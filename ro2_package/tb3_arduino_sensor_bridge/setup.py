from setuptools import find_packages, setup

package_name = 'tb3_arduino_sensor_bridge'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='changmin',
    maintainer_email='changmin@todo.todo',
    description='TODO: Package description',
    license='TODO: License declaration',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            "arduino_sensor_bridge_project = tb3_arduino_sensor_bridge.arduino_sensor_bridge_project:main",
            "touch_sensor_node = tb3_arduino_sensor_bridge.touch_sensor_node:main"
        ],
    },
)
