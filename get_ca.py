import re
import logging
import requests
from dotenv import load_dotenv
import os

load_dotenv(override=True)

api_key = os.getenv("OCR_API")

def get_text(data, type="url"):
    endpoint = "https://ocr-extract-text.p.rapidapi.com/ocr"
    headers = {
        "x-rapidapi-key": api_key,
        "x-rapidapi-host": "ocr-extract-text.p.rapidapi.com",
    }

    try:
        if type == "url":
            querystring = {"url": data}
            response = requests.get(endpoint, headers=headers, params=querystring)
        else:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            payload = {"base64": data}
            response = requests.post(endpoint, headers=headers, data=payload)

        response.raise_for_status()

        if response.text:
            response_json = response.json()
            print(f"response:", response_json.get("status"))
            if response_json.get("status"):
                return response_json.get("text")
            else:
                logging.error(f"OCR API returned an error: {response_json.get('error')}")
                return None
        else:
            logging.error("OCR API returned an empty response.")
            return None

    except requests.exceptions.RequestException as e:
        logging.error(f"Error during OCR API request: {e}")
        return None
    except ValueError as e:
        logging.error(f"Error decoding JSON response: {e}")
        return None


def get_contract_address(text) -> list:
    try:
        logging.info("Attempting to parse contract addresses from the text")
        pattern = r"\b(?:0x[a-fA-F0-9]{40}|[a-zA-Z0-9]{26,44})\b"
        
        matches = re.finditer(pattern, text)
        contract_addresses = []

        for match in matches:
            potential_address = match.group(0)
            
            # Basic filtering to reduce false positives
            if 26 <= len(potential_address) <= 44 or potential_address.startswith("0x"):
                logging.info(f"Found potential contract address: {potential_address}")
                contract_addresses.append(potential_address)
            else:
                logging.info(f"Matched string '{potential_address}' is likely not a valid contract address (filtered out).")
        
        return contract_addresses

    except Exception as e:
        logging.error(f"Error while parsing contract address: {e}")
        return []

def get_contract(tweet):
    logging.info("Attempting to parse contract addresses from the tweet")
    
    # First check tweet text
    if tweet.text and tweet.text.strip():  # Better check for non-empty text
        contracts = get_contract_address(tweet.text)
        if contracts:  # If contracts were found in text
            logging.info(f"Found contracts in tweet text: {contracts}")
            return contracts
    
    # If no contracts in text, check media
    if tweet.media:  # Simplified media check
        logging.info("No contracts found in tweet text, checking media")
        for media in tweet.media:
            if media.get("type") == "photo":
                image_url = media.get("media_url_https")
                logging.info(f"Processing image: {image_url}")
                
                text = get_text(data=image_url)
                if text:
                    contracts = get_contract_address(text)
                    if contracts:  # If contracts were found in image
                        logging.info(f"Found contracts in image: {contracts}")
                        return contracts
    
    logging.info("No contracts found in tweet text or media")
    return []

def main():
    while True:
        # Ask for image URL
        image_url = input("Enter image URL (press Enter to skip): ").strip()
        
        if image_url:
            # Test get_text function
            print("\nProcessing image...")
            text = get_text(data=image_url)
            if text:
                print("\nExtracted text from image:")
                print("-" * 50)
                print(text)
                print("-" * 50)
                
                print("\nSearching for contract addresses in the extracted text...")
                contracts = get_contract_address(text)
                if contracts:
                    print("\nFound contract addresses:")
                    for contract in contracts:
                        print(f"- {contract}")
                else:
                    print("\nNo contract addresses found in the image text.")
            else:
                print("\nFailed to extract text from the image.")
        
        # Ask for direct text input
        text_input = input("\nEnter text to scan for contracts (press Enter to skip): ").strip()
        
        if text_input:
            print("\nSearching for contract addresses in the input text...")
            contracts = get_contract_address(text_input)
            if contracts:
                print("\nFound contract addresses:")
                for contract in contracts:
                    print(f"- {contract}")
            else:
                print("\nNo contract addresses found in the text.")
        
        # Ask if user wants to continue
        if input("\nDo you want to test again? (y/n): ").lower() != 'y':
            break

if __name__ == "__main__":
    main()


 
