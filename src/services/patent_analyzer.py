import fitz  # PyMuPDF for PDF parsing
import re
import os
import tempfile
from PIL import Image
import logging
from typing import Dict, List, Any, Optional

# 設定日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PatentAnalyzer:
    """
    專利分析器 - 負責解析PDF並提取化學資訊
    """
    
    def __init__(self):
        self.temp_dirs = []
    
    def analyze_patent_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """
        分析專利PDF檔案
        
        Args:
            pdf_path: PDF檔案路徑
            
        Returns:
            包含分析結果的字典
        """
        try:
            result = {
                'chemical_formulas': [],
                'smiles_structures': [],
                'patent_elements': {},
                'analysis_summary': {},
                'images_extracted': 0,
                'pages_processed': 0
            }
            
            # Step 1: 提取文字內容和專利要素
            logger.info("開始提取PDF文字內容...")
            full_text, pages_processed = self._extract_text_from_pdf(pdf_path)
            result['pages_processed'] = pages_processed
            
            # Step 2: 提取專利要素
            logger.info("開始提取專利要素...")
            result['patent_elements'] = self._extract_patent_elements(full_text)
            
            # Step 3: 提取化學式
            logger.info("開始提取化學式...")
            result['chemical_formulas'] = self._extract_chemical_formulas(full_text)
            
            # Step 4: 提取圖像並嘗試識別化學結構
            logger.info("開始提取圖像...")
            images_extracted, smiles_list = self._extract_images_and_analyze(pdf_path)
            result['images_extracted'] = images_extracted
            result['smiles_structures'] = smiles_list
            
            # Step 5: 生成分析摘要
            logger.info("生成分析摘要...")
            result['analysis_summary'] = self._generate_analysis_summary(result)
            
            logger.info("專利分析完成")
            return result
            
        except Exception as e:
            logger.error(f"分析過程中發生錯誤: {str(e)}")
            raise e
    
    def _extract_text_from_pdf(self, pdf_path: str) -> tuple[str, int]:
        """從PDF提取文字內容"""
        try:
            pdf_doc = fitz.open(pdf_path)
            full_text = ''
            pages_processed = 0
            
            for page_num in range(len(pdf_doc)):
                page = pdf_doc.load_page(page_num)
                text = page.get_text()
                full_text += text + '\n'
                pages_processed += 1
            
            pdf_doc.close()
            return full_text, pages_processed
            
        except Exception as e:
            logger.error(f"PDF文字提取失敗: {str(e)}")
            return "", 0
    
    def _extract_patent_elements(self, full_text: str) -> Dict[str, str]:
        """使用正則表達式提取專利要素"""
        patent_elements = {}
        
        # 定義各種專利要素的正則表達式模式
        patterns = {
            'title': [
                r'Title of Invention\s*:?\s*(.*?)(?:\n|$)',
                r'發明名稱\s*:?\s*(.*?)(?:\n|$)',
                r'TITLE\s*:?\s*(.*?)(?:\n|$)',
                r'標題\s*:?\s*(.*?)(?:\n|$)'
            ],
            'abstract': [
                r'Abstract\s*:?\s*(.*?)(?=\n\n|\n[A-Z]|$)',
                r'摘要\s*:?\s*(.*?)(?=\n\n|\n[A-Z]|$)',
                r'ABSTRACT\s*:?\s*(.*?)(?=\n\n|\n[A-Z]|$)'
            ],
            'claims': [
                r'Claims?\s*:?\s*(.*?)(?=\n\n|\n[A-Z]|$)',
                r'請求項\s*:?\s*(.*?)(?=\n\n|\n[A-Z]|$)',
                r'CLAIMS?\s*:?\s*(.*?)(?=\n\n|\n[A-Z]|$)'
            ],
            'inventors': [
                r'Inventors?\s*:?\s*(.*?)(?:\n|$)',
                r'發明人\s*:?\s*(.*?)(?:\n|$)',
                r'INVENTORS?\s*:?\s*(.*?)(?:\n|$)'
            ],
            'applicant': [
                r'Applicants?\s*:?\s*(.*?)(?:\n|$)',
                r'申請人\s*:?\s*(.*?)(?:\n|$)',
                r'APPLICANTS?\s*:?\s*(.*?)(?:\n|$)'
            ],
            'description': [
                r'(?:Detailed )?Description\s*:?\s*(.*?)(?=\n\n|\n[A-Z]|$)',
                r'詳細說明\s*:?\s*(.*?)(?=\n\n|\n[A-Z]|$)',
                r'DESCRIPTION\s*:?\s*(.*?)(?=\n\n|\n[A-Z]|$)'
            ]
        }
        
        for element, pattern_list in patterns.items():
            for pattern in pattern_list:
                match = re.search(pattern, full_text, re.DOTALL | re.IGNORECASE | re.MULTILINE)
                if match:
                    content = match.group(1).strip()
                    if content and len(content) > 5:  # 確保內容有意義
                        patent_elements[element] = content[:500]  # 限制長度
                        break
        
        return patent_elements
    
    def _extract_chemical_formulas(self, text: str) -> List[str]:
        """提取化學式"""
        chemical_formulas = []
        
        # 定義化學式的正則表達式模式
        patterns = [
            # 基本化學式模式 (如 C6H6, H2SO4)
            r'\b[A-Z][a-z]?(?:\d+)?(?:[A-Z][a-z]?(?:\d+)?)*\b',
            # 複雜化學式 (包含括號)
            r'\b[A-Z][a-z]?(?:\d+)?(?:\([A-Z][a-z]?(?:\d+)?\)(?:\d+)?)*(?:[A-Z][a-z]?(?:\d+)?)*\b',
            # 有機化合物常見模式
            r'\bC\d+H\d+(?:[A-Z][a-z]?\d*)*\b'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                # 過濾掉太短或不像化學式的字符串
                if len(match) >= 2 and self._is_likely_chemical_formula(match):
                    if match not in chemical_formulas:
                        chemical_formulas.append(match)
        
        return chemical_formulas[:20]  # 限制數量
    
    def _is_likely_chemical_formula(self, formula: str) -> bool:
        """判斷字符串是否可能是化學式"""
        # 基本檢查：包含數字和大寫字母
        has_number = any(c.isdigit() for c in formula)
        has_uppercase = any(c.isupper() for c in formula)
        
        # 常見化學元素
        common_elements = ['C', 'H', 'O', 'N', 'S', 'P', 'Cl', 'Br', 'F', 'I', 'Na', 'K', 'Ca', 'Mg']
        has_common_element = any(elem in formula for elem in common_elements)
        
        # 避免常見的非化學式詞彙
        avoid_words = ['THE', 'AND', 'FOR', 'WITH', 'ARE', 'CAN', 'MAY', 'USE']
        is_avoid_word = formula.upper() in avoid_words
        
        return has_common_element and (has_number or len(formula) <= 6) and not is_avoid_word
    
    def _extract_images_and_analyze(self, pdf_path: str) -> tuple[int, List[str]]:
        """提取PDF中的圖像並嘗試分析化學結構"""
        try:
            pdf_doc = fitz.open(pdf_path)
            images_extracted = 0
            smiles_list = []
            
            # 建立臨時目錄
            temp_dir = tempfile.mkdtemp()
            self.temp_dirs.append(temp_dir)
            
            for page_num in range(len(pdf_doc)):
                page = pdf_doc.load_page(page_num)
                
                # 提取頁面圖像
                image_list = page.get_images()
                
                for img_index, img in enumerate(image_list):
                    try:
                        # 獲取圖像數據
                        xref = img[0]
                        pix = fitz.Pixmap(pdf_doc, xref)
                        
                        if pix.n - pix.alpha < 4:  # 確保不是CMYK
                            img_path = os.path.join(temp_dir, f'page_{page_num}_img_{img_index}.png')
                            pix.save(img_path)
                            images_extracted += 1
                            
                            # 嘗試分析化學結構 (這裡使用模擬結果)
                            smiles = self._analyze_chemical_structure_image(img_path)
                            if smiles:
                                smiles_list.append(smiles)
                        
                        pix = None
                        
                    except Exception as e:
                        logger.warning(f"處理圖像時發生錯誤: {str(e)}")
                        continue
            
            pdf_doc.close()
            return images_extracted, smiles_list
            
        except Exception as e:
            logger.error(f"圖像提取失敗: {str(e)}")
            return 0, []
    
    def _analyze_chemical_structure_image(self, image_path: str) -> Optional[str]:
        """
        分析化學結構圖像並轉換為SMILES
        注意：這裡使用模擬結果，實際應用中需要整合DECIMER或類似工具
        """
        try:
            # 檢查圖像是否存在且可讀取
            if not os.path.exists(image_path):
                return None
            
            # 使用PIL檢查圖像
            with Image.open(image_path) as img:
                width, height = img.size
                
                # 如果圖像太小，可能不是化學結構圖
                if width < 50 or height < 50:
                    return None
            
            # 模擬SMILES結果 (實際應用中應該使用DECIMER)
            mock_smiles = [
                'c1ccccc1',  # 苯環
                'CCO',       # 乙醇
                'CC(=O)O',   # 醋酸
                'c1ccc2ccccc2c1',  # 萘
                'CC(C)O'     # 異丙醇
            ]
            
            # 根據圖像特徵返回不同的SMILES (這裡隨機選擇)
            import random
            return random.choice(mock_smiles)
            
        except Exception as e:
            logger.warning(f"化學結構分析失敗: {str(e)}")
            return None
    
    def _generate_analysis_summary(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """生成分析摘要"""
        summary = {
            'total_compounds': len(result['chemical_formulas']),
            'total_structures': len(result['smiles_structures']),
            'pages_analyzed': result['pages_processed'],
            'images_found': result['images_extracted']
        }
        
        # 分析化合物類型
        compound_types = []
        for formula in result['chemical_formulas']:
            if 'C' in formula and 'H' in formula:
                compound_types.append('有機化合物')
            elif any(elem in formula for elem in ['Na', 'K', 'Ca', 'Mg']):
                compound_types.append('無機鹽類')
            else:
                compound_types.append('其他化合物')
        
        summary['compound_types'] = list(set(compound_types))
        
        # 評估專利強度 (簡單評估)
        patent_strength = '低'
        if result['patent_elements'].get('claims') and len(result['patent_elements']['claims']) > 100:
            patent_strength = '中等'
        if summary['total_compounds'] > 5:
            patent_strength = '高'
        
        summary['patent_strength'] = patent_strength
        summary['novelty_assessment'] = '需進一步評估'
        
        return summary
    
    def cleanup_temp_files(self):
        """清理臨時檔案"""
        for temp_dir in self.temp_dirs:
            try:
                import shutil
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"清理臨時檔案失敗: {str(e)}")
        self.temp_dirs.clear()
    
    def validate_smiles(self, smiles: str) -> bool:
        """驗證SMILES字符串的有效性 (簡化版本)"""
        try:
            # 簡單的SMILES格式檢查
            if not smiles or len(smiles) < 1:
                return False
            
            # 檢查是否包含有效的化學符號
            valid_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789()[]=#@+-')
            return all(c in valid_chars for c in smiles)
        except:
            return False
    
    def get_molecular_properties(self, smiles: str) -> Dict[str, Any]:
        """獲取分子性質 (簡化版本)"""
        try:
            # 返回基本資訊
            properties = {
                'smiles': smiles,
                'length': len(smiles),
                'contains_ring': '1' in smiles or 'c' in smiles.lower(),
                'estimated_complexity': 'simple' if len(smiles) < 10 else 'complex'
            }
            
            return properties
        except Exception as e:
            logger.warning(f"計算分子性質失敗: {str(e)}")
            return {}

