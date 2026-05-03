Project:
- Use python / FastAPI to ingest documents from bioRxiv and medRxiv from 2026 converting pdfs to mds (which parser to choose? Probably Docling). We will want to continuously poll for new data upon start of the server. (No-duplicates)
- We will use llamaindex for ingestion and retrieval of our mds, where we will push to Chroma our vector DB, we also need an easy way for the future of our UI to be able to only seach the vector DB for certain types of documents.
- Frontend will be Typescript + React

(Poll via AWS S3 bucket, we have a local code permitted IAM user named 'bio-view' with AmazonS3ReadOnlyAccess and AWSLambda_FullAccess)
