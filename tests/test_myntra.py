from app.pipelines.myntra_scraper import scrape_myntra_images

def test():
    url = "https://www.myntra.com/kurtas/kalini/kalini-ethnic-motifs-printed-mandarin-collar-straight-kurta/28375886/buy"
    print("Testing Myntra Scraper...")
    try:
        paths = scrape_myntra_images(url)
        print(f"Success! Downloaded {len(paths)} images:")
        for p in paths:
            print(f" - {p}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test()
