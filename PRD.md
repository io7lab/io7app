study https://github.com/io7lab/ to build a python io7 app server framework. the framework enables the user to specify the action for the event that way the IoT application can be easily built. the current folder has some rough ideas and prototypes, but you don't have stick on them.

The requirements:

  0. define a decorator which makes this possible
  1. user can specify/register the device + event topic and the action in python code with a function decorated by the decorator.
  2. the framework merge the device/events & the action and optimize the code so the corresponding python codes are executed for the specific device/events
  3. and when the user unregister the device/events & the action by the function name, the framework removes accordingly and optimize the code
  4. add inject decorator which mimics the nodered inject for the scheduling
  5. add examples folder with switch/lamp, thermostat/valve examples, some other examples from https://github.com/orgs/iotlab101/teams/iot201-2025/repositories   
  6. this library should be ligth not over blown, and helps the user develop the IoT App easy and make their code very clean and intuitive
  7. the payload always have 'd' for data, optionally 't' for timestamp. so if no 'd' just silently ignore. so make the library help the user app code can be further simplified with that setting. 
  8. one more thing, instead of config.py, let's use .env for the configuration
  9. document USER_GUIDE.md in terms of a brief intro of this library and how to use it for their program. This could be aligned with the test cases so the points on this doc are tested out
