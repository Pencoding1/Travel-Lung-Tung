from enum import Enum

class JUNK(str, Enum):
    Footer = '//*[@id="__next"]/div[4]'
    Header = '//*[@id="__next"]/div[1]/div[2]'
    Search_bar = '//*[@id="__next"]/div[3]/div[2]/div[1]/div'
    Sub_navigation = '//*[@id="__next"]/div[3]/div[2]/div[2]/div[1]',


class VEHICLES_LIST:
    BUTTON_LIST = [
        f'//*[@id="__next"]/div[3]/div[2]/div[9]/div/div[2]/div[2]/div[1]/div/div[{i}]'
        for i in range(1, 10)
    ]
    PARAGRAPH = '//*[@id="__next"]/div[3]/div[2]/div[9]/div/div[2]/div[2]/div[2]/div/div/div/p'
    CONTAINER = '//*[@id="__next"]/div[3]/div[2]/div[9]/div/div[2]/div[2]'

