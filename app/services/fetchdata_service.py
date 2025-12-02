# import os
# from .langchain_service import create_embeddings_and_store_text
# from .document_service import split_text_for_txt

# # Default fallback content for companies without knowledge base
# DEFAULT_NO_KNOWLEDGE_CONTENT = """
# I apologize, but this company hasn't uploaded any knowledge base content yet. 
# I'm unable to provide specific information about their products, services, or policies without proper documentation.

# Please contact the company directly for assistance, or ask them to upload their knowledge base content to enable me to help you better.
# """

# def get_default_no_knowledge_content():
#     """
#     Returns the default content when a company has no knowledge base.
    
#     Returns:
#         str: The default fallback message.
#     """
#     return DEFAULT_NO_KNOWLEDGE_CONTENT.strip()

# async def setup_default_knowledge_base(company_id: str):
#     """
#     Sets up a default knowledge base with fallback content for a company.
#     This is used when a company has no uploaded documents.
    
#     Args:
#         company_id: Company ID to set up default knowledge base for
#     """
#     from .langchain_service import create_company_vector_store
    
#     # Use the default fallback content
#     content = get_default_no_knowledge_content()
#     chunks = split_text_for_txt(content)
    
#     # Create company-specific knowledge base with fallback content
#     create_company_vector_store(company_id, chunks)