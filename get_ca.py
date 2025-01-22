import re
import logging

def get_contract_address(text: str) -> list:
    try:
        logging.info("Attempting to parse contract addresses from text")
        
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

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("script.log", mode='a')
        ]
    )

    # Test texts (same as before)
    texts = """
        "Check out this new token! CA: thisishelloieamazedift #ETH",
      
        """ 
    results = get_contract_address(f"{texts}")
    print(results)
 
