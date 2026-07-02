#!/usr/bin/env python3

import threading
from typing import List, Optional

import rclpy
from rclpy.node import Node

from std_msgs.msg import Bool
from std_msgs.msg import UInt8

import serial


START_BYTE = 0xAA
END_BYTE_1 = 0xAA
END_BYTE_2 = 0xEE

PKT_SENSOR_STATE = 0x31
PKT_SET_TOUCH = 0x41
PKT_SET_PHOTO_INTERRUPTER = 0x42
PKT_SET_BUZZER_MELODY = 0x43
PKT_SET_BUZZER = 0x44

PKT_PING = 0x7F

MAX_PAYLOAD_LEN = 32


class ParserState:
    WAIT_START_1 = 0
    WAIT_START_2 = 1
    WAIT_START_3 = 2
    READ_PACKET_ID = 3
    READ_LENGTH = 4
    READ_SEQUENCE = 5
    READ_PAYLOAD = 6
    READ_CHECKSUM = 7
    READ_END_1 = 8
    READ_END_2 = 9


class ArduinoSensorBridgeProject(Node):
    def __init__(self):
        super().__init__('arduino_sensor_bridge_project')

        self.declare_parameter('port', '/dev/ttyACM0')
        self.declare_parameter('baudrate', 115200)
        self.declare_parameter('read_period_sec', 0.005)
        self.declare_parameter('ping_period_sec', 1.0)

        self.port = self.get_parameter('port').value
        self.baudrate = int(self.get_parameter('baudrate').value)
        self.read_period_sec = float(self.get_parameter('read_period_sec').value)
        self.ping_period_sec = float(self.get_parameter('ping_period_sec').value)

        self.serial_port: Optional[serial.Serial] = None
        self.serial_lock = threading.Lock()

        self.tx_sequence = 0

        self.parser_state = ParserState.WAIT_START_1
        self.rx_packet_id = 0
        self.rx_length = 0
        self.rx_sequence = 0
        self.rx_payload: List[int] = []
        self.rx_checksum = 0

        # Publishers for sensor states
    
        self.touch_sensor_pub = self.create_publisher(
            Bool,
            '/touch_sensor/state',
            10
        )

        self.photo_interrupter_sensor_pub = self.create_publisher(
            Bool,
            '/photo_interrupter_sensor/state',
            10
        )

        self.buzzer_pub = self.create_publisher(
            Bool,
            '/buzzer/state',
            10
        )

        self.buzzer_melody_pub = self.create_publisher(
            Bool,
            '/buzzer/melody/state',
            10
        )

        self.rx_sequence_pub = self.create_publisher(
            UInt8,
            '/rx_sequence',
            10
        )

        # Subscriptions for commands from other nodes

        self.photo_interrupter_sensor_sub = self.create_subscription(
            Bool,
            '/photo_interrupter_sensor/cmd',
            self.photo_interrupter_sensor_callback,
            10
        )

        self.buzzer_sub = self.create_subscription(
            Bool,
            '/buzzer/cmd',
            self.buzzer_callback,
            10
        )

        self.buzzer_melody_sub = self.create_subscription(
            Bool,
            '/buzzer/melody/cmd',
            self.buzzer_melody_callback,
            10
        )

        self.open_serial()

        self.read_timer = self.create_timer(
            self.read_period_sec,
            self.read_serial_timer_callback
        )

        self.ping_timer = self.create_timer(
            self.ping_period_sec,
            self.ping_timer_callback
        )

    def open_serial(self):
        try:
            self.serial_port = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.0,
                write_timeout=0.1
            )

            self.serial_port.reset_input_buffer()
            self.serial_port.reset_output_buffer()

            self.get_logger().info(
                f'Opened serial port {self.port} at {self.baudrate} baud.'
            )

        except serial.SerialException as e:
            self.serial_port = None
            self.get_logger().error(
                f'Failed to open serial port {self.port}: {e}'
            )

    def calc_checksum(self,
                      packet_id: int,
                      length: int,
                      sequence: int,
                      payload: List[int]) -> int:
        checksum_sum = 0

        checksum_sum += packet_id
        checksum_sum += length
        checksum_sum += sequence

        for byte_value in payload:
            checksum_sum += byte_value

        return checksum_sum & 0xFF

    def send_packet(self, packet_id: int, payload: List[int]):
        if self.serial_port is None:
            return

        if not self.serial_port.is_open:
            return

        if len(payload) > 255:
            self.get_logger().error('Payload too large.')
            return

        length = len(payload)
        sequence = self.tx_sequence & 0xFF
        checksum = self.calc_checksum(packet_id, length, sequence, payload)

        packet = bytearray()
        packet.append(START_BYTE)
        packet.append(START_BYTE)
        packet.append(START_BYTE)

        packet.append(packet_id & 0xFF)
        packet.append(length & 0xFF)
        packet.append(sequence)

        for byte_value in payload:
            packet.append(byte_value & 0xFF)

        packet.append(checksum)

        packet.append(END_BYTE_1)
        packet.append(END_BYTE_2)

        try:
            with self.serial_lock:
                self.serial_port.write(packet)

            self.tx_sequence = (self.tx_sequence + 1) & 0xFF

        except serial.SerialException as e:
            self.get_logger().warn(f'Serial write failed: {e}')

    def clamp_color_to_u8(self, value: float) -> int:
        if value <= 0.0:
            return 0

        if value >= 1.0:
            return 255

        return int(value * 255.0)

    def photo_interrupter_sensor_callback(self, msg: Bool):
        photo_interrupter_sensor = 1 if msg.data else 0
        self.send_packet(PKT_SET_PHOTO_INTERRUPTER, [photo_interrupter_sensor])
        self.get_logger().info(f'Sent photo interrupter sensor command: {photo_interrupter_sensor}')

    def buzzer_callback(self, msg: Bool):
        buzzer = 1 if msg.data else 0
        self.send_packet(PKT_SET_BUZZER, [buzzer])
        self.get_logger().info(f'Sent buzzer command: {buzzer}')

    def buzzer_melody_callback(self, msg: Bool):
        buzzer_melody = 1 if msg.data else 0
        self.send_packet(PKT_SET_BUZZER_MELODY, [buzzer_melody])
        self.get_logger().info(f'Sent buzzer melody command: {buzzer_melody}')

    def ping_timer_callback(self):
        self.send_packet(PKT_PING, [])

    def read_serial_timer_callback(self):
        # 런타임 중 포트가 끊겼을 때의 자동 재연결 시도
        if self.serial_port is None or not self.serial_port.is_open:
            self.open_serial()
            return

        try:
            waiting = self.serial_port.in_waiting
            if waiting <= 0:
                return

            with self.serial_lock:
                data = self.serial_port.read(waiting)

            for byte_value in data:
                self.parse_byte(byte_value)
        except serial.SerialException as e:
            self.get_logger().warn(f'Serial read failed: {e}')
            if self.serial_port:
                try:
                    self.serial_port.close()
                except:
                    pass
                self.serial_port = None

    def reset_parser(self):
        self.parser_state = ParserState.WAIT_START_1
        self.rx_packet_id = 0
        self.rx_length = 0
        self.rx_sequence = 0
        self.rx_payload = []
        self.rx_checksum = 0

    def parse_byte(self, byte_in: int):
        byte_in = byte_in & 0xFF

        if self.parser_state == ParserState.WAIT_START_1:
            if byte_in == START_BYTE:
                self.parser_state = ParserState.WAIT_START_2

        elif self.parser_state == ParserState.WAIT_START_2:
            if byte_in == START_BYTE:
                self.parser_state = ParserState.WAIT_START_3
            else:
                self.parser_state = ParserState.WAIT_START_1

        elif self.parser_state == ParserState.WAIT_START_3:
            if byte_in == START_BYTE:
                self.parser_state = ParserState.READ_PACKET_ID
            else:
                self.parser_state = ParserState.WAIT_START_1

        elif self.parser_state == ParserState.READ_PACKET_ID:
            self.rx_packet_id = byte_in
            self.parser_state = ParserState.READ_LENGTH

        elif self.parser_state == ParserState.READ_LENGTH:
            self.rx_length = byte_in

            if self.rx_length > MAX_PAYLOAD_LEN:
                self.get_logger().warn(
                    f'Invalid payload length: {self.rx_length}'
                )
                self.reset_parser()
                return

            self.rx_payload = []
            self.parser_state = ParserState.READ_SEQUENCE

        elif self.parser_state == ParserState.READ_SEQUENCE:
            self.rx_sequence = byte_in

            if self.rx_length == 0:
                self.parser_state = ParserState.READ_CHECKSUM
            else:
                self.parser_state = ParserState.READ_PAYLOAD

        elif self.parser_state == ParserState.READ_PAYLOAD:
            self.rx_payload.append(byte_in)

            if len(self.rx_payload) >= self.rx_length:
                self.parser_state = ParserState.READ_CHECKSUM

        elif self.parser_state == ParserState.READ_CHECKSUM:
            self.rx_checksum = byte_in
            self.parser_state = ParserState.READ_END_1

        elif self.parser_state == ParserState.READ_END_1:
            if byte_in == END_BYTE_1:
                self.parser_state = ParserState.READ_END_2
            else:
                self.reset_parser()

        elif self.parser_state == ParserState.READ_END_2:
            if byte_in == END_BYTE_2:
                calculated = self.calc_checksum(
                    self.rx_packet_id,
                    self.rx_length,
                    self.rx_sequence,
                    self.rx_payload
                )

                if calculated == self.rx_checksum:
                    self.handle_packet(
                        self.rx_packet_id,
                        self.rx_length,
                        self.rx_sequence,
                        self.rx_payload
                    )
                else:
                    self.get_logger().warn(
                        'Checksum mismatch. '
                        f'packet_id=0x{self.rx_packet_id:02X}, '
                        f'rx=0x{self.rx_checksum:02X}, '
                        f'calc=0x{calculated:02X}'
                    )

            self.reset_parser()

        else:
            self.reset_parser()

    def handle_packet(self,
                      packet_id: int,
                      length: int,
                      sequence: int,
                      payload: List[int]):
        if packet_id == PKT_SENSOR_STATE:
            self.parse_sensor_state(length, sequence, payload)
        else:
            self.get_logger().debug(
                f'Unknown packet id: 0x{packet_id:02X}'
            )

    def parse_sensor_state(self,
                           length: int,
                           sequence: int,
                           payload: List[int]):
        if length != 4:
            self.get_logger().warn(
                f'Invalid sensor state payload length: {length}'
            )
            return

        # 터치 센서 모듈
        touch_sensor_state = payload[0] != 0
        # 포토 인터럽터 센서 모듈
        photo_interrupter_sensor_state = payload[1] != 0
        # 부저 모듈
        buzzer_state = payload[2] != 0
        # 부저 멜로디 모듈
        buzzer_melody_state = payload[3] != 0

        touch_msg = Bool()
        touch_msg.data = touch_sensor_state
        self.touch_sensor_pub.publish(touch_msg)

        photo_interrupter_msg = Bool()
        photo_interrupter_msg.data = photo_interrupter_sensor_state
        self.photo_interrupter_sensor_pub.publish(photo_interrupter_msg)

        buzzer_msg = Bool()
        buzzer_msg.data = buzzer_state
        self.buzzer_pub.publish(buzzer_msg)

        buzzer_melody_msg = Bool()
        buzzer_melody_msg.data = buzzer_melody_state
        self.buzzer_melody_pub.publish(buzzer_melody_msg)

        seq_msg = UInt8()
        seq_msg.data = sequence & 0xFF
        self.rx_sequence_pub.publish(seq_msg)


def main(args=None):
    rclpy.init(args=args)

    node = ArduinoSensorBridgeProject()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node.serial_port is not None and node.serial_port.is_open:
            node.serial_port.close()

        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
