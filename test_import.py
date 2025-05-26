# test_import.py
print("Attempting to import...")
try:
    from google_news_crawler import run_news_collection_pipeline
    print("Import successful!")
    print(f"Function object: {run_news_collection_pipeline}")
except ImportError as e:
    print(f"Import failed: {e}")
except Exception as e_gen:
    print(f"Some other error during import: {e_gen}")
    