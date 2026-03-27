from __future__ import absolute_import

#import makerbot_driver
import constants, errors, Encoder


def encode_payload(payload):
    """
    Encode passed payload into a packet.
    @param payload Command payload, 1 - n bytes describing the command to send
    @return bytearray containing the packet
    """
    if len(payload) > constants.maximum_payload_length:
        raise errors.PacketLengthError(len(payload), constants.maximum_payload_length)

    packet = bytearray()
    packet.append(constants.header)
    packet.append(len(payload))
    packet.extend(payload)
    packet.append(Encoder.CalculateCRC(payload))

    return packet


def decode_packet(packet):
    """
    Decode a packet from a payload.Non-streaming packet decoder.
    Accepts a byte array containing a single packet, and attempts
    to parse the packet and return the payload.
    @param packet byte array containing the input packet
    @return payload of the packet
    """
    assert type(packet) is bytearray

    if len(packet) < 4:
        raise errors.PacketLengthError(len(packet), 4)

    if packet[0] != constants.header:
        raise errors.PacketHeaderError(packet[0], constants.header)

    if packet[1] != len(packet) - 3:
        raise errors.PacketLengthFieldError(packet[1], len(packet) - 3)

    if packet[len(packet) - 1] != Encoder.CalculateCRC(packet[2:(len(packet) - 1)]):
        raise errors.PacketCRCError(packet[len(packet) - 1], Encoder.CalculateCRC(packet[2:(len(packet) - 1)]))

    return packet[2:(len(packet) - 1)]


def check_response_code(response_code):
    """
    Check the response code, and return if succesful, or raise an appropriate exception
    """
    if response_code == constants.response_code_dict['SUCCESS']:
        return

    elif response_code == constants.response_code_dict['GENERIC_PACKET_ERROR']:
        raise errors.GenericError()

    elif response_code == constants.response_code_dict['ACTION_BUFFER_OVERFLOW']:
        raise errors.BufferOverflowError()

    elif response_code == constants.response_code_dict['CRC_MISMATCH']:
        raise errors.CRCMismatchError()

    elif response_code == constants.response_code_dict['COMMAND_NOT_SUPPORTED']:
        raise errors.CommandNotSupportedError()

    elif response_code == constants.response_code_dict['DOWNSTREAM_TIMEOUT']:
        raise errors.DownstreamTimeoutError()

    elif response_code == constants.response_code_dict['TOOL_LOCK_TIMEOUT']:
        raise errors.ToolLockError()

    elif response_code == constants.response_code_dict['CANCEL_BUILD']:
        raise errors.BuildCancelledError()

    elif response_code == constants.response_code_dict['ACTIVE_LOCAL_BUILD']:
        raise errors.ActiveBuildError()

    elif response_code == constants.response_code_dict['OVERHEAT_STATE']:
        raise errors.OverheatError()

    raise errors.UnknownResponseError(response_code)


class PacketStreamDecoder(object):

    """
    A state machine that accepts bytes from an s3g packet stream, checks the validity of
    each packet, then extracts and returns the payload.
    """
    def __init__(self):
        """
        Initialize the packet decoder
        """
        self.state = 'WAIT_FOR_HEADER'
        self.payload = bytearray()
        self.expected_length = 0

    def parse_byte(self, byte):
        """
        Entry point, call for each byte added to the stream.
        @param byte Byte to add to the stream
        """

        if self.state == 'WAIT_FOR_HEADER':
            if byte != constants.header:
                raise errors.PacketHeaderError(byte, constants.header)

            self.state = 'WAIT_FOR_LENGTH'

        elif self.state == 'WAIT_FOR_LENGTH':
            if byte > constants.maximum_payload_length:
                raise errors.PacketLengthFieldError(byte, constants.maximum_payload_length)

            self.expected_length = byte
            self.state = 'WAIT_FOR_DATA'

        elif self.state == 'WAIT_FOR_DATA':
            self.payload.append(byte)
            if len(self.payload) == self.expected_length:
                self.state = 'WAIT_FOR_CRC'

        elif self.state == 'WAIT_FOR_CRC':
            if Encoder.CalculateCRC(self.payload) != byte:
                raise errors.PacketCRCError(byte, Encoder.CalculateCRC(self.payload))

            self.state = 'PAYLOAD_READY'

        else:
            raise Exception('Parser in bad state: too much data provided?')
