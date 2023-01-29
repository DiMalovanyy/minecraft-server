import asyncio
import argparse
import logging
import sys
import enum

# Utils (TODO: Move to module)

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def initDefaultLogger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    return logger

# ============================================================================================
        
class ClientMode(enum.Enum):
    READING_MODE = 1
    WRITING_MODE = 2

class Client:
    def __init__(self, loop, message_reader):
        self.loop = loop
        self.message_reader = message_reader
        self.logger = initDefaultLogger(__class__.__name__)
        # Client start in reading mode
        self.client_mode = ClientMode.READING_MODE
        self.message_buffer = []

        self.switch_after_reading_inactive_sec = 2
        self.switch_writer_mode_task = self.loop.call_later(
            self.switch_after_reading_inactive_sec, 
            self.__switch_to_writing_mode
        )
    
    async def connect(self, address, port):
        self.reader, self.writer = await asyncio.open_connection(address, port)
        self.logger.info("Connection opened")
        self.loop.create_task(self.__reading_task())

    async def __writing_task(self, message):
        self.writer.write(message.encode())
        await self.writer.drain()

    async def __reading_task(self):
        line = await self.reader.readuntil(separator=b'\n')
        if line:
            # Reset switching to writer mode since input come
            self.switch_writer_mode_task.cancel()
            self.switch_writer_mode_task = self.loop.call_later(
                self.switch_after_reading_inactive_sec, 
                self.__switch_to_writing_mode
            )
            if self.client_mode == ClientMode.READING_MODE:
                self.__print_message_from_server(line.decode())
            else:
                self.message_buffer.append(line.decode())
            self.loop.create_task(self.__reading_task())


    @staticmethod
    def __print_message_from_server(message):
        print(f"{bcolors.OKBLUE}server{bcolors.ENDC}> {message}", end="")

    @staticmethod
    def __print_mode_switched_to(mode):
        print("{} Mode swiched to {}{}".format(
            bcolors.FAIL,
            ("WritingMode" if mode == ClientMode.WRITING_MODE else "ReadingMode"),
            bcolors.ENDC
        ))

    def __switch_to_writing_mode(self):
        self.client_mode = ClientMode.WRITING_MODE
        print("{}Mode swiched to {} since there is no input for {} seconds (Press Enter to switch) {}".format(
            bcolors.FAIL,
            "WritingMode",
            self.switch_after_reading_inactive_sec,
            bcolors.ENDC
        ))
        self.__user_input_task()

    def __switch_to_reading_mode(self):
        self.client_mode = ClientMode.READING_MODE
        # print("{}Mode swiched to {}{}".format(
        #     bcolors.FAIL,
        #     "ReadingMode",
        #     bcolors.ENDC
        # ))
        for message in self.message_buffer:
            self.__print_message_from_server(message)
        self.message_buffer = []
        self.switch_writer_mode_task = self.loop.call_later(
            self.switch_after_reading_inactive_sec, 
            self.__switch_to_writing_mode
        )


    def __user_input_task(self):
        sys.stdout.flush()
        data = input(f"{bcolors.OKGREEN}client{bcolors.ENDC}> ")
        if data != "":
            self.loop.create_task(self.__writing_task(data + "\n"))
        
        self.__switch_to_reading_mode()


    async def disconnect(self):
        self.writer.close()
        await self.writer.wait_closed()


def main():
    parser = argparse.ArgumentParser(
        description="Client to redirector",
    )
    parser.add_argument("address", type=str)
    parser.add_argument("port", type=str)
    parser.add_argument("--ssl_cert", type=str, required=False)
    args = parser.parse_args()

    loop = asyncio.new_event_loop()
    client = Client(loop, lambda msg: print(msg))
    loop.create_task(client.connect(args.address, int(args.port)))

    loop.run_forever()

if __name__ == "__main__":
    main()