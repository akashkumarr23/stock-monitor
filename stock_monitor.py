import requests
import time
import json
import re
from datetime import datetime
import logging
from bs4 import BeautifulSoup
import os
from urllib.parse import urlparse, quote
from typing import List, Dict, Set, Optional

class IntegratedStockMonitor:
    def __init__(self, bot_token: str, chat_id: str, screener_urls: List[str], check_interval: int = 300):
        """
        Integrated Stock Monitor using the screening logic from your Dart code
        
        Args:
            bot_token (str): Telegram bot token
            chat_id (str): Telegram chat ID
            screener_urls (List[str]): List of screener URLs to monitor
            check_interval (int): Check interval in seconds (default: 5 minutes)
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.screener_urls = screener_urls if isinstance(screener_urls, list) else [screener_urls]
        self.check_interval = check_interval
        self.telegram_api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        
        # Store stocks for each URL (like your Dart code)
        self.url_stocks: Dict[str, Set[str]] = {}
        
        # Initialize storage for each URL
        for url in self.screener_urls:
            self.url_stocks[url] = set()
        
        # Default selectors from your Dart code
        self.default_selectors = {
            'finviz.com': ['.screener-link', '.screener-body-cell'],
            'yahoo.com': ['.ticker', '.symbol'],
            'marketwatch.com': ['.symbol', '.ticker'],
            'seekingalpha.com': ['.symbol', '.ticker'],
            'stocktwits.com': ['.symbol', '.ticker'],
            'scanx.trade': [
                'table tbody tr td:first-child',
                'tr td:first-child',
                'td:first-child',
                '.stock-name',
                '[data-stock-name]',
                'td',
            ],
        }
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('integrated_monitor.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def get_stocks_from_url(self, url: str) -> List[str]:
        """
        Main stock extraction method based on your Dart getStocksFromUrl function
        """
        try:
            self.logger.info(f'Fetching URL: {url}')
            
            # Headers from your Dart code
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0',
            }
            
            response = requests.get(url, headers=headers, timeout=30)
            
            self.logger.info(f'Response status: {response.status_code}')
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                stocks = []
                
                # Special handling for scanX.trade (from your Dart code)
                domain = urlparse(url).hostname.lower()
                if 'scanx.trade' in domain:
                    self.logger.info('Detected scanX.trade, using special extraction method')
                    stocks.extend(self._extract_from_scanx(soup))
                    if stocks:
                        self.logger.info(f'Found {len(stocks)} stocks from scanX.trade: {stocks}')
                        return list(set(stocks))  # Remove duplicates
                
                # Get selectors for this domain
                selectors = self._get_default_selectors(url)
                
                # Try each selector
                for selector in selectors:
                    try:
                        elements = soup.select(selector)
                        self.logger.info(f'Trying selector "{selector}" - found {len(elements)} elements')
                        
                        for element in elements:
                            text = element.get_text().strip()
                            self.logger.debug(f'Element text: "{text}"')
                            if self._is_valid_stock_symbol(text):
                                stocks.append(text)
                                self.logger.debug(f'Added stock: "{text}"')
                        
                        # If we found stocks with this selector, break
                        if stocks:
                            self.logger.info(f'Found stocks with selector "{selector}", stopping')
                            break
                    except Exception as e:
                        self.logger.debug(f'Error with selector {selector}: {e}')
                        continue
                
                # If no stocks found with selectors, try table-based extraction
                if not stocks:
                    stocks.extend(self._extract_from_tables(soup))
                
                return list(set(stocks))  # Remove duplicates
            else:
                self.logger.error(f'HTTP Error: {response.status_code} - {response.reason}')
                
        except Exception as e:
            self.logger.error(f'Error fetching stocks from URL: {e}')
            if 'CORS' in str(e) or 'ClientException' in str(e):
                self.logger.info('This might be a CORS issue. Trying fallback methods...')
                return self._get_stocks_with_fallback(url)
        
        return []

    def _extract_from_scanx(self, soup: BeautifulSoup) -> List[str]:
        """
        ScanX.trade specific extraction method (from your Dart _extractFromScanX)
        """
        stocks = []
        
        try:
            self.logger.info('Starting scanX.trade specific extraction...')
            
            # Method 1: Look for table rows with stock data
            table_rows = soup.select('table tbody tr')
            self.logger.info(f'Found {len(table_rows)} table rows')
            
            for row in table_rows:
                cells = row.select('td')
                if cells:
                    # First cell usually contains the stock name
                    first_cell = cells[0].get_text().strip()
                    self.logger.debug(f'First cell text: "{first_cell}"')
                    
                    if first_cell and len(first_cell) > 3:
                        # Clean up the stock name (remove extra whitespace, etc.)
                        clean_name = re.sub(r'\s+', ' ', first_cell).strip()
                        if ' ' in clean_name and len(clean_name) >= 5:
                            stocks.append(clean_name)
                            self.logger.debug(f'Added stock name: "{clean_name}"')
            
            # Method 2: Look for specific stock name elements
            if not stocks:
                stock_elements = soup.select('[class*="stock"], [class*="name"], [data-stock]')
                self.logger.info(f'Found {len(stock_elements)} stock name elements')
                
                for element in stock_elements:
                    text = element.get_text().strip()
                    self.logger.debug(f'Stock element text: "{text}"')
                    if text and len(text) > 3:
                        clean_name = re.sub(r'\s+', ' ', text).strip()
                        if ' ' in clean_name and len(clean_name) >= 5:
                            stocks.append(clean_name)
                            self.logger.debug(f'Added stock name: "{clean_name}"')
            
            # Method 3: Look for any text that looks like a stock name
            if not stocks:
                all_text_elements = soup.select('td, div, span')
                self.logger.info(f'Checking {len(all_text_elements)} text elements')
                
                for element in all_text_elements:
                    text = element.get_text().strip()
                    if text and 10 < len(text) < 100:
                        # Look for patterns like "Company Name NSE" or "Company Name BSE"
                        if ' ' in text and ('NSE' in text or 'BSE' in text or '&' in text):
                            clean_name = re.sub(r'\s+', ' ', text).strip()
                            if len(clean_name) >= 5:
                                stocks.append(clean_name)
                                self.logger.debug(f'Added potential stock: "{clean_name}"')
            
            self.logger.info(f'scanX.trade extraction complete. Found {len(stocks)} stocks')
            
        except Exception as e:
            self.logger.error(f'Error in scanX.trade extraction: {e}')
        
        return stocks

    def _extract_from_tables(self, soup: BeautifulSoup) -> List[str]:
        """
        Table-based extraction method (from your Dart _extractFromTables)
        """
        stocks = []
        
        try:
            # Look for table rows
            table_rows = soup.select('tr')
            for row in table_rows:
                cells = row.select('td, th')
                if cells:
                    # Try first cell as potential stock name/symbol
                    first_cell = cells[0].get_text().strip()
                    if self._is_valid_stock_symbol(first_cell):
                        stocks.append(first_cell)
                    
                    # Also check other cells for stock symbols
                    for i in range(1, min(len(cells), 3)):
                        cell_text = cells[i].get_text().strip()
                        if self._is_valid_stock_symbol(cell_text):
                            stocks.append(cell_text)
            
            # If no stocks found in regular table cells, try looking for specific stock name elements
            if not stocks:
                stock_name_elements = soup.select('[class*="stock"], [class*="name"], [data-stock]')
                for element in stock_name_elements:
                    text = element.get_text().strip()
                    if self._is_valid_stock_symbol(text):
                        stocks.append(text)
            
            self.logger.info(f'Found {len(stocks)} stocks from table extraction')
            
        except Exception as e:
            self.logger.error(f'Error extracting from tables: {e}')
        
        return stocks

    def _is_valid_stock_symbol(self, text: str) -> bool:
        """
        Stock symbol validation (from your Dart _isValidStockSymbol)
        """
        if not text or len(text) > 50:
            return False
        
        # Clean the text - remove extra whitespace and normalize
        clean_text = text.strip()
        if not clean_text:
            return False
        
        # For scanX.trade, we're looking for stock names like "Bajaj Holdings & Investments"
        # These are typically longer than traditional stock symbols
        if ' ' in clean_text:
            # This looks like a full stock name
            return 3 <= len(clean_text) <= 50
        
        # Stock symbols should be alphanumeric and typically uppercase
        symbol_text = re.sub(r'[^A-Za-z0-9]', '', clean_text)
        if not symbol_text:
            return False
        
        # Common stock symbol patterns
        patterns = [
            r'^[A-Z]{1,5}$',           # 1-5 uppercase letters (US stocks)
            r'^[A-Z]{1,4}\.[A-Z]{1,2}$',  # NYSE/NASDAQ format
            r'^[A-Z]{1,3}[0-9]{1,2}$',    # Some exchanges use numbers
            r'^[A-Z]{2,15}$',          # Indian stock symbols (longer names)
            r'^[A-Z]{1,10}[0-9]{1,2}$',   # Indian stocks with numbers
        ]
        
        return any(re.match(pattern, symbol_text) for pattern in patterns)

    def _get_default_selectors(self, url: str) -> List[str]:
        """
        Get default selectors for a domain (from your Dart _getDefaultSelectors)
        """
        domain = urlparse(url).hostname.lower()
        
        for key, selectors in self.default_selectors.items():
            if key in domain:
                return selectors
        
        # Default selectors for unknown websites
        return [
            '.stock-symbol',
            '.ticker',
            '.symbol',
            '[data-symbol]',
            '.stock',
            '.ticker-symbol',
        ]

    def _get_stocks_with_fallback(self, url: str) -> List[str]:
        """
        Fallback method for CORS issues (from your Dart getStocksFromUrlWithFallback)
        """
        try:
            self.logger.info('Trying fallback method...')
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                return self._extract_from_scanx(soup)
        except Exception as e:
            self.logger.error(f'Fallback method also failed: {e}')
        
        return []

    def get_stocks_with_proxy(self, url: str) -> List[str]:
        """
        CORS proxy method (from your Dart getStocksFromUrlWithProxy)
        """
        try:
            self.logger.info('Trying CORS proxy method...')
            
            # Use a CORS proxy service
            proxy_url = f'https://api.allorigins.win/raw?url={quote(url)}'
            
            response = requests.get(
                proxy_url,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
                timeout=30
            )
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                domain = urlparse(url).hostname.lower()
                
                if 'scanx.trade' in domain:
                    return self._extract_from_scanx(soup)
                else:
                    return self._extract_from_tables(soup)
        except Exception as e:
            self.logger.error(f'CORS proxy method failed: {e}')
        
        return []

    def get_new_stocks_for_url(self, url: str) -> List[str]:
        """
        Get new stocks for a specific URL (similar to your Dart getNewStocks)
        """
        current_stocks = set(self.get_stocks_from_url(url))
        last_stocks = self.url_stocks.get(url, set())
        
        new_stocks = current_stocks - last_stocks
        
        # Update stored stocks if we found any
        if current_stocks:
            self.url_stocks[url] = current_stocks
        
        return list(new_stocks)

    def perform_stock_screening_for_all_urls(self) -> Dict[str, List[str]]:
        """
        Screen all URLs and return new stocks (similar to your Dart performStockScreeningForAllUrls)
        """
        all_new_stocks = {}
        
        for url in self.screener_urls:
            try:
                self.logger.info(f'Screening URL: {url}')
                new_stocks = self.get_new_stocks_for_url(url)
                all_new_stocks[url] = new_stocks
                self.logger.info(f'Found {len(new_stocks)} new stocks for URL: {url}')
            except Exception as e:
                self.logger.error(f'Error screening URL {url}: {e}')
                all_new_stocks[url] = []
        
        return all_new_stocks

    def send_telegram_message(self, message: str) -> bool:
        """
        Send message to Telegram
        """
        try:
            payload = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': 'HTML'
            }
            
            response = requests.post(self.telegram_api_url, data=payload, timeout=10)
            response.raise_for_status()
            
            self.logger.info("Telegram message sent successfully")
            return True
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error sending Telegram message: {e}")
            return False

    def format_stock_message(self, url: str, new_stocks: List[str]) -> str:
        """
        Format stock alert message
        """
        try:
            domain = urlparse(url).hostname
            
            if len(new_stocks) == 1:
                stock = new_stocks[0]
                message = f"""
🚨 <b>New Stock Alert!</b>

📈 <b>Stock:</b> {stock}
🌐 <b>Source:</b> {domain}
⏰ <b>Detected:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

<a href="{url}">🔗 View Screener</a>
"""
            else:
                stocks_list = '\n'.join([f'• {stock}' for stock in new_stocks[:10]])  # Limit to 10
                more_text = f'\n... and {len(new_stocks) - 10} more' if len(new_stocks) > 10 else ''
                
                message = f"""
🚨 <b>{len(new_stocks)} New Stocks Alert!</b>

📈 <b>New Stocks:</b>
{stocks_list}{more_text}

🌐 <b>Source:</b> {domain}
⏰ <b>Detected:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

<a href="{url}">🔗 View Screener</a>
"""
            
            return message.strip()
            
        except Exception as e:
            self.logger.error(f"Error formatting message: {e}")
            return f"🔔 New stocks detected from {urlparse(url).hostname}: {', '.join(new_stocks[:5])}"

    def test_all_urls(self) -> Dict[str, bool]:
        """
        Test all URLs and return success status
        """
        results = {}
        
        for url in self.screener_urls:
            try:
                stocks = self.get_stocks_from_url(url)
                results[url] = len(stocks) > 0
                self.logger.info(f"URL {url}: {'✅ Success' if results[url] else '❌ Failed'} - Found {len(stocks)} stocks")
                if stocks:
                    self.logger.info(f"Sample stocks: {stocks[:5]}")
            except Exception as e:
                results[url] = False
                self.logger.error(f"URL {url}: ❌ Error - {e}")
        
        return results

    def run_monitor(self):
        """
        Main monitoring loop
        """
        self.logger.info("Starting Integrated Stock Monitor...")
        
        # Test all URLs first
        self.logger.info("Testing all URLs...")
        test_results = self.test_all_urls()
        
        working_urls = [url for url, success in test_results.items() if success]
        failed_urls = [url for url, success in test_results.items() if not success]
        
        if not working_urls:
            self.logger.error("❌ No working URLs found. Please check your screener URLs.")
            return
        
        if failed_urls:
            self.logger.warning(f"⚠️ These URLs failed: {failed_urls}")
        
        # Send startup message
        startup_message = f"""
🤖 <b>Integrated Stock Monitor Started!</b>

✅ <b>Working URLs:</b> {len(working_urls)}
❌ <b>Failed URLs:</b> {len(failed_urls)}
⏱️ <b>Check Interval:</b> {self.check_interval // 60} minutes
🔍 <b>Method:</b> Advanced Web Scraping
🕒 <b>Started:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Ready to monitor for new stocks! 📈
"""
        self.send_telegram_message(startup_message)
        
        # Initial screening to populate data
        self.logger.info("Performing initial screening...")
        self.perform_stock_screening_for_all_urls()
        
        # Main monitoring loop
        while True:
            try:
                self.logger.info(f"Waiting {self.check_interval} seconds before next check...")
                time.sleep(self.check_interval)
                
                # Screen all URLs for new stocks
                all_new_stocks = self.perform_stock_screening_for_all_urls()
                
                # Send alerts for new stocks
                for url, new_stocks in all_new_stocks.items():
                    if new_stocks:
                        message = self.format_stock_message(url, new_stocks)
                        self.send_telegram_message(message)
                        time.sleep(2)  # Delay between messages
                
            except KeyboardInterrupt:
                self.logger.info("Monitor stopped by user")
                self.send_telegram_message("🛑 Integrated Monitor stopped by user")
                break
            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")
                time.sleep(60)  # Wait before retrying

# Usage
if __name__ == "__main__":
    # Get credentials from environment variables
    BOT_TOKEN = os.getenv('BOT_TOKEN', '8490011483:AAGLet1WFFoVQnHSGUdhnkPSDvaHQYZaxoY')
    CHAT_ID = os.getenv('CHAT_ID', '8454924509')
    
    # Your screener URLs (can be multiple)
    # Method 1: Get from environment variable (recommended for production)
    SCREENER_URLS_ENV = os.getenv('SCREENER_URLS', '')
    
    if SCREENER_URLS_ENV:
        # Split multiple URLs by comma if provided via environment
        SCREENER_URLS = [url.strip() for url in SCREENER_URLS_ENV.split(',') if url.strip()]
    else:
        # Method 2: Hardcode your URLs here (easy for testing)
        SCREENER_URLS = [
            "https://scanx.trade/stock-screener/high-price-3-above-ltp-high-price-5-above-open-volume-20d-vol-sma-x-2-nifty-500-246593",
            # Add more URLs here by uncommenting and modifying:
            # "https://scanx.trade/stock-screener/your-different-screener-12345",
            # "https://screener.in/screens/your-screen/",
            # "https://chartink.com/screener/your-scan",
        ]

    if BOT_TOKEN == '8490011483:AAGLet1WFFoVQnHSGUdhnkPSDvaHQYZaxoY' or CHAT_ID == '8454924509':
        print("❌ Please set your credentials!")
        print("\nSet environment variables:")
        print("export BOT_TOKEN='your_bot_token_here'")
        print("export CHAT_ID='your_chat_id_here'")
        print("\nOr replace the values directly in the code")
        exit(1)
    
    # Create and run monitor
    monitor = IntegratedStockMonitor(
        bot_token=BOT_TOKEN,
        chat_id=CHAT_ID,
        screener_urls=SCREENER_URLS,
        check_interval=300  # 5 minutes
    )
    
    try:
        monitor.run_monitor()
    except Exception as e:
        print(f"Monitor failed to start: {e}")

"""
📋 INSTALLATION REQUIREMENTS:

pip install requests beautifulsoup4 lxml

🔗 HOW TO CHANGE SCREENER URLs:

METHOD 1 - Environment Variable (Recommended):
export SCREENER_URLS="https://scanx.trade/your-new-screener-url-123456"

For multiple URLs, separate with commas:
export SCREENER_URLS="url1,url2,url3"

METHOD 2 - Direct Code Edit:
Change the SCREENER_URLS list in the code:
SCREENER_URLS = [
    "https://scanx.trade/your-new-screener-url",
    "https://another-screener.com/your-screen",
]

METHOD 3 - Runtime (Interactive):
Add this function to change URLs while running:

def update_urls_interactive():
    new_urls = input("Enter new URLs (comma-separated): ").split(',')
    return [url.strip() for url in new_urls if url.strip()]

# Then call: monitor.screener_urls = update_urls_interactive()

EXAMPLES OF URL CHANGES:

✅ Different ScanX Screener:
"https://scanx.trade/stock-screener/different-criteria-789012"

✅ Multiple ScanX Screeners:
"https://scanx.trade/stock-screener/screener-1-123456"
"https://scanx.trade/stock-screener/screener-2-789012"

✅ Other Platforms:
"https://screener.in/screens/your-custom-screen/"
"https://chartink.com/screener/your-scan-name"

🎯 KEY FEATURES FROM YOUR DART CODE:

✅ EXACT SCANX.TRADE LOGIC:
- Uses your _extractFromScanX method
- Special handling for stock names vs symbols
- Multiple extraction fallbacks

✅ MULTI-URL SUPPORT:
- Monitor multiple screener URLs
- Track stocks separately for each URL
- Detect new stocks per URL (like your Dart code)

✅ ROBUST EXTRACTION:
- Table-based extraction
- Custom selectors per domain
- CORS proxy fallback
- Multiple retry methods

✅ SMART STOCK VALIDATION:
- Uses your _isValidStockSymbol logic
- Handles both symbols and full company names
- Pattern matching for different markets

✅ PRODUCTION READY:
- Comprehensive error handling
- Detailed logging
- Graceful fallbacks
- URL testing before monitoring

🚀 USAGE:
1. Set your BOT_TOKEN and CHAT_ID
2. Change URLs using any method above
3. Run: python integrated_monitor.py

The code uses the EXACT same logic as your working Dart code! 🎯
"""