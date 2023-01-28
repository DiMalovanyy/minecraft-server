import asyncio
import argparse
import logging
from functools import partial
import uuid

def initDefaultLogger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
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
    def __init__(self, loop, id, address, input_handler, deletion_handler):
        self.loop = loop
        self.address = address
        self.input_handler = input_handler
        self.id = id
        self.deletion_handler = deletion_handler
        self.logger = initDefaultLogger(f"{__class__.__name__}({address}) {id}")
        self.logger.info("Connection established")

    async def start_session(self, reader, writer):
        await writer.drain()
        self.send_message = async_partial(self.__send_to_writer, writer)
        self.loop.create_task(self.__client_reading_task(reader))

    async def send(self, message):
        # self.logger.debug("Send message: {}".format(message))
        await self.send_message(message)

    
    async def __send_to_writer(self, writer_stream, message):
        if writer_stream.transport._conn_lost:
            self.deletion_handler()
            return
        try:
            writer_stream.write(message.encode())
            await writer_stream.drain()
            # self.logger.debug("Send message: {}".format(message))
        except (ConnectionResetError, BrokenPipeError) as ex:
            self.deletion_handler()

    async def __client_reading_task(self, reader):
        try:
            line = await reader.readline()
            if line:
                self.input_handler(line)
        except (ConnectionResetError, BrokenPipeError) as ex:
            self.deletion_handler()


class SslServer: 
    class ProcessOutputBuffer:
        def __init__(self, server):
            self.buffer = ""
            self.server = server

        def write(self, msg, need_flush=False):
            self.buffer += msg.decode()
            if need_flush:
                self.__flush()

        def __flush(self):
            # self.server.logger.debug("Buffer: {} flushed to clients".format(self.buffer))
            for client_id, client_session in self.server.sessions.items():
                self.server.loop.create_task(client_session.send(self.buffer))
            self.buffer = ""

    def __init__(self, loop, client_input_handler):
        self.loop = loop
        self.sessions = {}
        self.client_input_handler = client_input_handler
        self.output_buffer = self.ProcessOutputBuffer(self)
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
            deletion_handler=lambda: self.__handle_client_removal(client_id)
        )
        self.sessions[client_id] = client_session
        self.logger.info("Client session added: {}".format(client_id))
        self.loop.create_task(client_session.start_session(reader, writer))

    def __handle_client_removal(self, client_id):
        self.logger.info("Client session deleted: {}".format(client_id))
        del self.sessions[client_id]


class ExecutableProcess:
    def __init__(self, loop, executable_name):
        self.loop = loop
        self.executable_name = executable_name
        self.logger = initDefaultLogger(f"{__class__.__name__}-{self.executable_name}")
        self.buffer_flush_characters=b'\x3e'


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
        
        if line.startswith(self.buffer_flush_characters):
            callback(line, True)
        else:
            callback(line, False)
        await self.__process_read_task(out_stream, callback)
        
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
            lambda msg: self.loop.create_task(executable.process_write(msg.encode()))
        )

        # Start ExecutableProcess with async task on received messages from stdout and stderr
        loop.create_task(
            executable.start(
                lambda msg, need_buf_flush: self.__on_process_message_received(False, server.output_buffer.write, msg, need_buf_flush), 
                lambda msg, need_buf_flush: self.__on_process_message_received(True, None, msg, need_buf_flush)
            )
        )
        loop.create_task(server.start(9998)) 
        loop.run_forever()

        self.logger.info('Successfully finished')

    def __on_process_message_received(self, isStderr, handler, message, need_buffer_flush):
        if isStderr:
            self.logger.warning("[Process Stderr]: {}".format(message))
        else:
            # self.logger.debug("[Message from process]: {}. Need Buffer Flush: {}".format(message, need_buffer_flush))
            handler(message, need_buffer_flush)

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
