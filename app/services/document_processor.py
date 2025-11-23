import os
import aiofiles
from typing import List
from pypdf import PdfReader
from docx import Document as DocxDocument
from app.core.config import settings


class DocumentProcessor:
    """Обработчик документов для извлечения текста"""
    
    @staticmethod
    async def process_pdf(file_path: str) -> str:
        """Обработка PDF файла"""
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    
    @staticmethod
    async def process_docx(file_path: str) -> str:
        """Обработка DOCX файла"""
        doc = DocxDocument(file_path)
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        return text
    
    @staticmethod
    async def process_txt(file_path: str) -> str:
        """Обработка TXT файла"""
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
            text = await f.read()
        return text
    
    @staticmethod
    async def process_document(file_path: str, file_type: str) -> str:
        """Обработка документа по типу"""
        if file_type == "pdf":
            return await DocumentProcessor.process_pdf(file_path)
        elif file_type == "docx":
            return await DocumentProcessor.process_docx(file_path)
        elif file_type == "txt":
            return await DocumentProcessor.process_txt(file_path)
        else:
            raise ValueError(f"Unsupported file type: {file_type}")
    
    @staticmethod
    def split_text_into_chunks(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
        """Разделение текста на фрагменты"""
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            chunks.append(chunk)
            start = end - overlap
        
        return chunks

