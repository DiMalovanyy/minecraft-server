import asyncio
import argparse
import logging
import uuid


# Note!!!(dmalovan): Change log level to see adition debug info
def initDefaultLogger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    return logger

def async_partial(f, *args):
   async def f2(*args2):
       result = f(*args, *args2)
       if asyncio.iscoroutinefunction(f):
           result = await result
       return result
   return f2

class ClientSession:
    def __init__(self, loop, id, address, input_handler, deletion_handler, drain_buffer):
        self.loop = loop
        self.address = address
        self.input_handler = input_handler
        self.drain_buffer = drain_buffer
        self.id = id
        self.delete = deletion_handler
        self.logger = initDefaultLogger(f"{__class__.__name__}({address}) {id}")
        self.logger.info("Connection established")

    async def start_session(self, reader, writer):
        await writer.drain()
        self.send_message = async_partial(self.__send_to_writer, writer)
        # Send to connected client existed buffer
        self.drain_buffer()
        self.loop.create_task(self.__client_reading_task(reader))

    async def send(self, message):
        # self.logger.debug("Send message: {}".format(message))
        await self.send_message(message)

    
    async def __send_to_writer(self, writer_stream, message):
        if writer_stream.transport._conn_lost:
            self.delete()
            return
        try:
            writer_stream.write(message.encode())
            await writer_stream.drain()
        except (ConnectionResetError, BrokenPipeError) as ex:
            self.logger.warning("Connection will deleted: {}".format(ex))
            self.delete()

    async def __client_reading_task(self, reader):
        try:
            line = await reader.readline()
            if line:
                self.logger.info("Input from client: {}".format(line))
                self.input_handler(line)

            self.loop.create_task(self.__client_reading_task(reader))
        except (ConnectionResetError, BrokenPipeError) as ex:
            self.logger.warning("Connection will deleted: {}".format(ex))
            self.delete()


class SslServer: 
    class ProcessOutputBuffer:
        def __init__(self, server, loop):
            self.buffer = ""
            self.server = server
            self.loop = loop
            self.lock = asyncio.Lock()
            self.need_clear_on_next_input = False
            self.buffer_flush_after_seconds = 1
            self.buffer_flush_sheduled_on = self.loop.time()
            self.flush_buffer_task = loop.call_later(
                self.buffer_flush_after_seconds, 
                self.__schedule_buffer_flush)

        def write(self, msg):
            # Schedule Buffer flush task on write, if another write occured task will recreated
            self.flush_buffer_task.cancel()
            self.buffer_flush_sheduled_on = self.loop.time()
            self.flush_buffer_task = self.loop.call_later(self.buffer_flush_after_seconds, self.__schedule_buffer_flush)

            if self.need_clear_on_next_input:
                self.buffer = ""
                self.need_clear_on_next_input = False
            self.buffer += msg.decode()

        # Buffer flush rule:
        #   Clear buffer and send it to clients if there is no message from process for self.buffer_flush_sheduled_on sec
        #   Note(dmalovan): There is no problem if buffer flushed but not all data was written
        def __schedule_buffer_flush(self):
            if self.buffer != "" and not self.need_clear_on_next_input:
                self.server.logger.info("Buffer flushed by scheduled task, since nobody write to it for {} seconds".format(
                    self.loop.time() - self.buffer_flush_sheduled_on
                ))
                self.__flush()

        def __flush(self):
            for client_id, client_session in self.server.sessions.items():
                self.server.loop.create_task(client_session.send(self.buffer))
            self.need_clear_on_next_input = True

    def __init__(self, loop, client_input_handler):
        self.loop = loop
        self.sessions = {}
        self.client_input_handler = client_input_handler
        self.output_buffer = self.ProcessOutputBuffer(self, loop)
        self.logger = initDefaultLogger(__class__.__name__)

    async def start(self, port):
        self.logger.info("Start listening on {}".format(port))
        self.server = await asyncio.start_server(self.__handle_connection, '127.0.0.1', port)
        
        async with self.server:
            await self.server.serve_forever()
        
        self.logger.info("Finished")

    async def __handle_connection(self, reader, writer):
        client_id = uuid.uuid4()
        client_session = ClientSession(
            self.loop, 
            client_id, 
            writer.get_extra_info('peername'), 
            input_handler=self.client_input_handler,
            deletion_handler=lambda: self.__handle_client_removal(client_id),
            drain_buffer=lambda: self.__drain_buffer_to_session(client_id)
        )
        self.sessions[client_id] = client_session
        self.logger.info("Client session added: {}".format(client_id))
        self.loop.create_task(client_session.start_session(reader, writer))

    def __handle_client_removal(self, client_id):
        if client_id in self.sessions:
            self.logger.info("Client session deleted: {}".format(client_id))
            del self.sessions[client_id]


    def __drain_buffer_to_session(self, session_id):
        if session_id in self.sessions:
            self.loop.create_task(
                self.sessions[session_id].send(self.output_buffer.buffer)
            )


class ExecutableProcess:
    def __init__(self, loop, executable_name):
        self.loop = loop
        self.executable_name = executable_name
        self.logger = initDefaultLogger(f"{__class__.__name__}-{self.executable_name}")


    async def start(self, stdout_cb, stderr_cb):
        self.process = await asyncio.create_subprocess_exec(
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            program=self.executable_name)
        self.logger.info("Started")
        self.loop.create_task(self.__process_handle_exit(stdout_cb, stderr_cb))
        self.loop.create_task(self.__process_read_task(self.process.stdout, stdout_cb))
        self.loop.create_task(self.__process_read_task(self.process.stderr, stderr_cb))


    async def __process_read_task(self, out_stream, callback):
        line = await out_stream.readline()
        if not line or self.process.returncode != None:
            return
        
        callback(line)
        self.loop.create_task(self.__process_read_task(out_stream, callback))
        
    async def __process_handle_exit(self, stdout_cb, stderr_cb):
        returncode = await self.process.wait()
        self.logger.info("Process exited with code {}".format(returncode))
        stdout_cb(bytes(), True)
        # stderr_cb(bytes(), True) Don't need for now
        

    async def process_write(self, bytes):
        self.process.stdin.write(bytes)
        await self.process.stdin.drain()

class Redirector:
    def __init__(self, binary, cert_dir):
        self.binary = binary
        self.cert_dir = cert_dir
        self.logger = initDefaultLogger(__class__.__name__)

    def start(self):
        self.logger.info('Started with binary {}'.format(self.binary))
            # Create new asyncio event loop, it will handle all task
        loop = asyncio.new_event_loop()

        executable = ExecutableProcess(loop, self.binary)

        # Instance of SslServer will be able to write to ExecutableProcess by triggering handler (2 arg)
        # by SslServer clients
        server = SslServer(
            loop, 
            lambda bytes: loop.create_task(executable.process_write(bytes))
        )

        # Start ExecutableProcess with async task on received messages from stdout and stderr
        loop.create_task(
            executable.start(
                lambda msg: self.__on_process_message_received(False, server.output_buffer.write, msg), 
                lambda msg: self.__on_process_message_received(True, None, msg)
            )
        )
        loop.create_task(server.start(9998)) 
        loop.run_forever()

        self.logger.info('Successfully finished')

    def __on_process_message_received(self, isStderr, handler, message):
        if isStderr:
            self.logger.warning("[Process Stderr]: {}".format(message))
        else:
            handler(message)

def main():
    parser = argparse.ArgumentParser(
        description="redirect stdout/stdin to client socket via ssl connection",
    )
    parser.add_argument("--binary",  type=str, required=True)
    parser.add_argument("--ssl_cert", type=str, required=False)
    args = parser.parse_args()


    proxy_server = Redirector(args.__dict__['binary'], None)
    proxy_server.start()

if __name__ == "__main__": 
    main()
