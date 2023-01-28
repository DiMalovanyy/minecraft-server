import asyncio
import argparse
import logging
import sys

def initDefaultLogger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    return logger



class Client:

    def __init__(self, loop, message_reader):
        self.loop = loop
        self.message_reader = message_reader
        self.logger = initDefaultLogger(__class__.__name__)
    
    async def connect(self, address, port):
        reader, writer = await asyncio.open_connection(address, port)
        self.logger.info("Connection opened")
        self.loop.create_task(self.__reading_task(reader))

    async def write(self, message):
        self.writer.write(message.encode())
        await self.writer.drain()

    async def __reading_task(self, reader):
        line = await reader.read(100)
        if line:
            self.logger.debug("Mesage: {}".format(line.decode()))
            self.loop.create_task(self.__reading_task(reader))

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