import requests
from bs4 import BeautifulSoup
import json
import datetime
import time
import os
import sys
from typing import List, Dict
import base64
import re

class HuggingFacePapersScraper:
    def __init__(self, slack_webhook_url: str, github_token: str, github_repo: str, github_owner: str):
        self.slack_webhook_url = slack_webhook_url
        self.github_token = github_token
        self.github_repo = github_repo
        self.github_owner = github_owner
        self.base_url = "https://huggingface.co/papers"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def scrape_papers(self, date_str: str = None) -> List[Dict]:
        if date_str:
            url = f"{self.base_url}/date/{date_str}"
        else:
            url = self.base_url
        
        print(f"Scraping URL: {url}")
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            print(f"Response status: {response.status_code}")
            
            soup = BeautifulSoup(response.content, 'html.parser')
            papers = []
            
            selectors_to_try = [
                'article',
                'div[class*="paper"]',
                'div[class*="card"]',
                'div[class*="item"]',
                'a[href*="/papers/"]',
                'div[class*="border"]'
            ]
            
            found_elements = []
            for selector in selectors_to_try:
                elements = soup.select(selector)
                if elements:
                    print(f"Found {len(elements)} elements with selector: {selector}")
                    found_elements = elements
                    break
            
            if not found_elements:
                links = soup.find_all('a', href=True)
                paper_links = [link for link in links if '/papers/' in link.get('href', '')]
                print(f"Found {len(paper_links)} paper links")
                
                # Process ALL paper links found (removed limit)
                for link in paper_links:
                    try:
                        href = link.get('href', '')
                        if href.startswith('/'):
                            full_url = f"https://huggingface.co{href}"
                        else:
                            full_url = href
                        
                        title = link.get_text(strip=True)
                        if not title:
                            title = "No title available"
                        
                        parent = link.parent
                        authors = "Unknown authors"
                        abstract = "No abstract available"
                        
                        if parent:
                            author_patterns = [
                                r'(\d+)\s+authors?',
                                r'by\s+([^·]+)',
                                r'·\s*([^·]+)\s*authors?'
                            ]
                            
                            parent_text = parent.get_text()
                            for pattern in author_patterns:
                                match = re.search(pattern, parent_text, re.IGNORECASE)
                                if match:
                                    authors = match.group(1).strip()
                                    break
                            
                            text_parts = parent_text.split('·')
                            if len(text_parts) > 1:
                                for part in text_parts:
                                    if 'author' not in part.lower() and len(part.strip()) > 10:
                                        abstract = part.strip()[:200]
                                        break
                        
                        if title and len(title) > 3:
                            if abstract == "No abstract available":
                                abstract = ""
                            papers.append({
                                'title': title,
                                'authors': authors,
                                'abstract': abstract,
                                'link': full_url,
                                'scraped_at': datetime.datetime.now().isoformat()
                            })
                        
                    except Exception as e:
                        print(f"Error processing link: {e}")
                        continue
            
            else:
                for element in found_elements:
                    try:
                        title = "No title"
                        link = ""
                        authors = "Unknown authors"
                        abstract = "No abstract available"
                        
                        title_selectors = ['h1', 'h2', 'h3', 'h4', '.title', '[class*="title"]']
                        for selector in title_selectors:
                            title_elem = element.select_one(selector)
                            if title_elem:
                                title = title_elem.get_text(strip=True)
                                break
                        
                        if not title or title == "No title":
                            title = element.get_text(strip=True)[:100]
                        
                        link_elem = element.find('a', href=True)
                        if link_elem:
                            href = link_elem.get('href', '')
                            if href.startswith('/'):
                                link = f"https://huggingface.co{href}"
                            else:
                                link = href
                        
                        element_text = element.get_text()
                        author_match = re.search(r'(\d+)\s+authors?', element_text, re.IGNORECASE)
                        if author_match:
                            authors = f"{author_match.group(1)} authors"
                        
                        text_parts = element_text.split('·')
                        if len(text_parts) > 2:
                            abstract = text_parts[-1].strip()[:200]
                        
                        if title and len(title) > 3:
                            if abstract == "No abstract available":
                                abstract = ""
                            papers.append({
                                'title': title,
                                'authors': authors,
                                'abstract': abstract,
                                'link': link,
                                'scraped_at': datetime.datetime.now().isoformat()
                            })
                    except Exception as e:
                        print(f"Error processing element: {e}")
                        continue
            
            # Only filter out papers with very short titles, but no artificial limits
            papers = [p for p in papers if p['title'] and len(p['title']) > 5]
            
            print(f"Successfully scraped {len(papers)} papers")
            return papers
            
        except Exception as e:
            print(f"Error scraping papers: {e}")
            return []

    def post_to_slack(self, papers: List[Dict]) -> bool:
        if not papers:
            print("No papers to post to Slack")
            return False
        
        try:
            # Handle large number of papers by splitting into multiple messages if needed
            # Slack has a limit of ~50 blocks per message, so we'll chunk if necessary
            max_papers_per_message = 20  # Conservative limit to avoid Slack API limits
            
            for chunk_index, chunk_start in enumerate(range(0, len(papers), max_papers_per_message)):
                chunk_papers = papers[chunk_start:chunk_start + max_papers_per_message]
                
                blocks = [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"📚 Latest Papers Update - {datetime.datetime.now().strftime('%Y-%m-%d')}"
                        }
                    }
                ]
                
                # Add chunk info if there are multiple chunks
                if len(papers) > max_papers_per_message:
                    blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Part {chunk_index + 1} of {(len(papers) - 1) // max_papers_per_message + 1}* - Showing papers {chunk_start + 1}-{min(chunk_start + len(chunk_papers), len(papers))} of {len(papers)} total"
                        }
                    })
                
                blocks.append({"type": "divider"})
                
                # Add all papers in this chunk
                for paper in chunk_papers:
                    paper_block = {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*{paper['title']}*\n_{paper['authors']}_" + (f"\n{paper['abstract'][:150]}..." if paper['abstract'] else "")
                        }
                    }
                    
                    if paper['link']:
                        paper_block["accessory"] = {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Read Paper"
                            },
                            "url": paper['link']
                        }
                    
                    blocks.append(paper_block)
                    blocks.append({"type": "divider"})
                
                payload = {
                    "text": f"📚 {len(papers)} new papers available",
                    "blocks": blocks
                }
                
                print(f"Posting chunk {chunk_index + 1} to Slack ({len(chunk_papers)} papers)")
                response = requests.post(self.slack_webhook_url, json=payload, timeout=30)
                response.raise_for_status()
                
                # Small delay between chunks to avoid rate limiting
                if chunk_index < (len(papers) - 1) // max_papers_per_message:
                    time.sleep(1)
            
            print(f"Successfully posted all {len(papers)} papers to Slack")
            return True
            
        except Exception as e:
            print(f"Error posting to Slack: {e}")
            return False

    def log_to_github(self, papers: List[Dict]) -> bool:
        if not papers:
            print("No papers to log to GitHub")
            return False
        
        try:
            today = datetime.datetime.now().strftime('%Y-%m-%d')
            filename = f"papers_log_{today}.json"
            
            print(f"Logging to GitHub repo: {self.github_owner}/{self.github_repo}")
            
            existing_content = self.get_github_file_content(filename)
            if existing_content:
                try:
                    existing_papers = json.loads(existing_content)
                    existing_titles = {p['title'] for p in existing_papers}
                    new_papers = [p for p in papers if p['title'] not in existing_titles]
                    all_papers = existing_papers + new_papers
                    print(f"Found {len(existing_papers)} existing papers, adding {len(new_papers)} new ones")
                except json.JSONDecodeError:
                    all_papers = papers
            else:
                all_papers = papers
                print(f"Creating new log file with {len(papers)} papers")
            
            content = json.dumps(all_papers, indent=2, ensure_ascii=False)
            encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
            
            url = f"https://api.github.com/repos/{self.github_owner}/{self.github_repo}/contents/logs/{filename}"
            headers = {
                'Authorization': f'token {self.github_token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            sha = self.get_github_file_sha(filename)
            
            payload = {
                "message": f"Update papers log for {today} - {len(all_papers)} papers",
                "content": encoded_content,
                "branch": "main"
            }
            
            if sha:
                payload["sha"] = sha
                print("Updating existing file")
            else:
                print("Creating new file")
            
            response = requests.put(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            print(f"Successfully logged all {len(all_papers)} papers to GitHub")
            return True
            
        except Exception as e:
            print(f"Error logging to GitHub: {e}")
            return False

    def get_github_file_content(self, filename: str) -> str:
        try:
            url = f"https://api.github.com/repos/{self.github_owner}/{self.github_repo}/contents/logs/{filename}"
            headers = {
                'Authorization': f'token {self.github_token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                return base64.b64decode(data['content']).decode('utf-8')
            return None
        except Exception as e:
            print(f"Error getting GitHub file content: {e}")
            return None

    def get_github_file_sha(self, filename: str) -> str:
        try:
            url = f"https://api.github.com/repos/{self.github_owner}/{self.github_repo}/contents/logs/{filename}"
            headers = {
                'Authorization': f'token {self.github_token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                return data['sha']
            return None
        except Exception as e:
            print(f"Error getting GitHub file SHA: {e}")
            return None

    def run_scraper(self, date_str: str = None) -> Dict:
        print(f"Starting scraper at {datetime.datetime.now()}")
        
        papers = self.scrape_papers(date_str)
        print(f"Scraped {len(papers)} papers")
        
        if papers:
            print("Sample paper:", papers[0])
        
        slack_success = self.post_to_slack(papers)
        print(f"Slack posting: {'Success' if slack_success else 'Failed'}")
        
        github_success = self.log_to_github(papers)
        print(f"GitHub logging: {'Success' if github_success else 'Failed'}")
        
        return {
            'papers_count': len(papers),
            'slack_success': slack_success,
            'github_success': github_success,
            'timestamp': datetime.datetime.now().isoformat()
        }

def main():
    # Updated environment variable names that comply with GitHub's requirements
    SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL')
    HF_GITHUB_TOKEN = os.getenv('HF_GITHUB_TOKEN')  # Changed from GITHUB_TOKEN
    HF_REPO_NAME = os.getenv('HF_REPO_NAME')        # Changed from GITHUB_REPO
    HF_REPO_OWNER = os.getenv('HF_REPO_OWNER')      # Changed from GITHUB_OWNER
    
    if not all([SLACK_WEBHOOK_URL, HF_GITHUB_TOKEN, HF_REPO_NAME, HF_REPO_OWNER]):
        print("Error: Missing required environment variables")
        print("Required: SLACK_WEBHOOK_URL, HF_GITHUB_TOKEN, HF_REPO_NAME, HF_REPO_OWNER")
        sys.exit(1)
    
    scraper = HuggingFacePapersScraper(
        slack_webhook_url=SLACK_WEBHOOK_URL,
        github_token=HF_GITHUB_TOKEN,
        github_repo=HF_REPO_NAME,
        github_owner=HF_REPO_OWNER
    )
    
    date_str = None
    if len(sys.argv) > 1:
        date_str = sys.argv[1]
    
    result = scraper.run_scraper(date_str)
    print(f"Scraper completed: {result}")

if __name__ == "__main__":
    main()