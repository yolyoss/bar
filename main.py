
from musicbot import xenoichi
from highrise.__main__ import *

room_id = "687d9840026e8689afecf1ed"
bot_token = "09b08c1a548fecf3720463585e6f1963013a74af6796b0fec3dfcdac4bab9b48"

if __name__ == "__main__":
    definitions = [BotDefinition(xenoichi(), room_id, bot_token)]
    arun(main(definitions))
