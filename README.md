# LLM Papers Updates 

Automated fetches latest papers from HuggingFace daily and posts them to Slack.

## Features

-  **Daily automation** at 10:00 AM IST
-  **Slack notifications** with formatted paper heading

## Usage

- **Automatic**: Runs daily at 10:00 AM IST
- **Manual**: Go to Actions tab → Run workflow
- **Specific date**: Use manual trigger with date in YYYY-MM-DD format

## Structure

```
├── scraper.py              # Main scraper script
├── requirements.txt        # Dependencies
├── .github/workflows/      # GitHub Actions workflow
└── logs/                   # Daily paper logs (auto-generated)
```

## Sample Output

Papers are posted to Slack with:
- Paper title and authors
- Direct link to paper

Daily logs are saved as JSON files in the `logs/` directory.

---

*Scrapes papers from [HuggingFace Papers](https://huggingface.co/papers) and delivers them to your Slack channel automatically.*
