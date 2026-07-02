import rclpy
from rclpy.node import Node

from std_msgs.msg import Bool
from nav_msgs.msg import Odometry

class TouchSensorNode(Node):
    def __init__(self):
        super().__init__("touch_sensor_node")
        self.get_logger().info("Touch Sensor Node has been started.")

        self.touch_sensor_subscriber = self.create_subscription(
            Bool,
            "/touch_sensor/state",
            self.touch_sensor_callback,
            10
        )

        self.photo_interrupter_sensor_subscriber = self.create_subscription(
            Bool,
            "/photo_interrupter_sensor/state",
            self.photo_interrupter_sensor_callback,
            10
        )

        self.buzzer_subscriber = self.create_subscription(
            Bool,
            "/buzzer/state",
            self.buzzer_callback,
            10
        )

        self.buzzer_melody_subscriber = self.create_subscription(
            Bool,
            "/buzzer/melody/state",
            self.buzzer_melody_callback,
            10
        )


        self.photo_interrupter_sensor_pub = self.create_publisher(
            Bool,
            "/photo_interrupter_sensor/cmd",
            10
        )

        self.buzzer_pub = self.create_publisher(
            Bool,   
            "/buzzer/cmd", 10
        )

        self.buzzer_melody_pub = self.create_publisher(
            Bool,
            "/buzzer/melody/cmd",
            10
        )

    


    def touch_sensor_callback(self, msg: Bool):
        # self.get_logger().info(f'Sent touch sensor command: {msg.data}')
        prev_msg = msg.data
        if prev_msg != msg.data and msg.data == True:
            self.get_logger().info(f'Touch sensor state True: {msg.data}')

    def buzzer_callback(self, msg: Bool):
        self.buzzer_pub.publish(msg)
        # self.get_logger().info(f'Sent buzzer command: {msg.data}')

    def buzzer_melody_callback(self, msg: Bool):
        self.buzzer_melody_pub.publish(msg)
        # self.get_logger().info(f'Sent buzzer melody command: {msg.data}')

    def photo_interrupter_sensor_callback(self, msg: Bool):
        self.photo_interrupter_sensor_pub.publish(msg)
        # self.get_logger().info(f'Photo interrupter sensor state: {msg.data}')
                
def main(args=None):
    rclpy.init(args=args)
    touch_sensor_node = TouchSensorNode()

    try:
        rclpy.spin(touch_sensor_node)
    except KeyboardInterrupt:
        pass
    finally:
        touch_sensor_node.destroy_node()
        rclpy.shutdown()

if __name__ == "__main__":
    main()

