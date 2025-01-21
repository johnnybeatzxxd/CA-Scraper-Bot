import asyncio
from dotenv import load_dotenv
import os
from twikit import Client, Tweet
import threading
from get_client import get_or_create_client  
from send_message import send_message_to_bot
import json
import logging
import random

load_dotenv()

main_loop = None
main_thread = None

def start_script():

    global main_thread
    global main_loop

    if main_thread is None or not main_thread.is_alive():
        # Create a new event loop for the thread
        main_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(main_loop)

        # get configs
        with open("configs.json","r",encoding='utf-8') as f:
            configs = json.load(f)

        target = configs.get("target")
        if target is None or target == "":
            return "Target is not set"

        interval  = configs.get("interval")
        if interval is None or interval == "": 
            return "Interval is not set"
        print(f"target: {target} interval: {interval}")

        # Start the main function in a separate thread
        from main import main 
        main_thread = threading.Thread(target=lambda: main_loop.run_until_complete(main(target,interval)))
        main_thread.start()
        return "Script started!"
    else:
      return "Script is already running!"

def stop_script():
    global main_thread
    global main_loop

    if main_thread is not None and main_thread.is_alive():
        from main import stop_main  
        stop_main()

        main_loop.call_soon_threadsafe(main_loop.stop)
        main_thread.join()

        return "Script stopped!"
    else:
        return "Script is not running!"


