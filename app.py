# app.py
from flask import Flask
import threading
import asyncio
from main import main, stop_main  

app = Flask(__name__)
main_loop = None
main_thread = None

@app.route('/')
def hello():
    return "Hello, World!"

@app.route('/start')
def start_script():
    global main_thread
    global main_loop

    if main_thread is None or not main_thread.is_alive():
      # Create a new event loop for the thread
      main_loop = asyncio.new_event_loop()
      asyncio.set_event_loop(main_loop)

      # Start the main function in a separate thread
      main_thread = threading.Thread(target=lambda: main_loop.run_until_complete(main()))
      main_thread.start()
      return "<p>Script started!</p>"
    else:
      return "<p>Script is already running!</p>"

@app.route('/stop')
def stop_script():
    global main_thread
    global main_loop

    if main_thread is not None and main_thread.is_alive():
        # Stop the main function
        stop_main()

        # Stop the event loop and wait for the thread to finish
        main_loop.call_soon_threadsafe(main_loop.stop)
        main_thread.join()

        return "<p>Script stopped!</p>"
    else:
        return "<p>Script is not running!</p>"

if __name__ == "__main__":
    app.run(debug=True)

