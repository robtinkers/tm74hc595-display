import TM74HC595
d=TM74HC595.Display(sclk=14,rclk=12,dio=13,displays=4)
d.demo()