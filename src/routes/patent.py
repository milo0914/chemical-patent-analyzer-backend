from flask import Blueprint, jsonify, request, current_app
import os
import tempfile
import uuid
import threading
import time
from werkzeug.utils import secure_filename
from flask_cors import cross_origin
from src.services.patent_analyzer import PatentAnalyzer

patent_bp = Blueprint('patent', __name__)

ALLOWED_EXTENSIONS = {'pdf'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# 儲存分析任務狀態
analysis_tasks = {}
analyzer = PatentAnalyzer()

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def run_analysis(task_id, file_path, temp_dir):
    """在背景執行分析任務"""
    try:
        # 更新狀態為處理中
        analysis_tasks[task_id]['status'] = 'processing'
        analysis_tasks[task_id]['progress'] = 10
        analysis_tasks[task_id]['message'] = '開始分析PDF檔案...'
        
        # 執行分析
        result = analyzer.analyze_patent_pdf(file_path)
        
        # 更新進度
        analysis_tasks[task_id]['progress'] = 90
        analysis_tasks[task_id]['message'] = '生成分析報告...'
        
        # 儲存結果
        analysis_tasks[task_id]['status'] = 'completed'
        analysis_tasks[task_id]['progress'] = 100
        analysis_tasks[task_id]['message'] = '分析完成'
        analysis_tasks[task_id]['result'] = result
        
        # 清理檔案
        try:
            os.remove(file_path)
            os.rmdir(temp_dir)
        except:
            pass
            
    except Exception as e:
        analysis_tasks[task_id]['status'] = 'failed'
        analysis_tasks[task_id]['message'] = f'分析失敗: {str(e)}'
        analysis_tasks[task_id]['error'] = str(e)

@patent_bp.route('/upload', methods=['POST'])
@cross_origin()
def upload_patent():
    """
    上傳專利PDF檔案並開始分析
    """
    try:
        # 檢查是否有檔案
        if 'file' not in request.files:
            return jsonify({'error': '沒有檔案被上傳'}), 400
        
        file = request.files['file']
        
        # 檢查檔案名稱
        if file.filename == '':
            return jsonify({'error': '沒有選擇檔案'}), 400
        
        # 檢查檔案類型
        if file and allowed_file(file.filename):
            # 生成唯一的檔案名稱和任務ID
            task_id = str(uuid.uuid4())
            unique_filename = str(uuid.uuid4()) + '.pdf'
            
            # 建立臨時目錄
            temp_dir = tempfile.mkdtemp()
            file_path = os.path.join(temp_dir, unique_filename)
            
            # 儲存檔案
            file.save(file_path)
            
            # 檢查檔案大小
            file_size = os.path.getsize(file_path)
            if file_size > MAX_FILE_SIZE:
                os.remove(file_path)
                os.rmdir(temp_dir)
                return jsonify({'error': '檔案大小超過限制 (50MB)'}), 400
            
            # 初始化任務狀態
            analysis_tasks[task_id] = {
                'status': 'pending',
                'progress': 0,
                'message': '等待處理...',
                'filename': file.filename,
                'created_at': time.time()
            }
            
            # 在背景執行分析
            thread = threading.Thread(target=run_analysis, args=(task_id, file_path, temp_dir))
            thread.daemon = True
            thread.start()
            
            return jsonify({
                'message': '檔案上傳成功，開始分析',
                'task_id': task_id,
                'filename': file.filename
            }), 200
        
        else:
            return jsonify({'error': '不支援的檔案格式，請上傳PDF檔案'}), 400
            
    except Exception as e:
        return jsonify({'error': f'上傳失敗: {str(e)}'}), 500

@patent_bp.route('/analyze/<task_id>', methods=['GET'])
@cross_origin()
def get_analysis_result(task_id):
    """
    取得專利分析結果
    """
    try:
        if task_id not in analysis_tasks:
            return jsonify({'error': '找不到指定的分析任務'}), 404
        
        task = analysis_tasks[task_id]
        
        if task['status'] == 'completed':
            return jsonify({
                'task_id': task_id,
                'status': task['status'],
                'result': task['result']
            }), 200
        elif task['status'] == 'failed':
            return jsonify({
                'task_id': task_id,
                'status': task['status'],
                'error': task.get('error', '未知錯誤')
            }), 500
        else:
            return jsonify({
                'task_id': task_id,
                'status': task['status'],
                'progress': task['progress'],
                'message': task['message']
            }), 202  # 202 Accepted - 仍在處理中
        
    except Exception as e:
        return jsonify({'error': f'取得結果失敗: {str(e)}'}), 500

@patent_bp.route('/status/<task_id>', methods=['GET'])
@cross_origin()
def get_analysis_status(task_id):
    """
    取得分析狀態
    """
    try:
        if task_id not in analysis_tasks:
            return jsonify({'error': '找不到指定的分析任務'}), 404
        
        task = analysis_tasks[task_id]
        
        return jsonify({
            'task_id': task_id,
            'status': task['status'],
            'progress': task['progress'],
            'message': task['message'],
            'filename': task.get('filename', ''),
            'created_at': task.get('created_at', 0)
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'狀態查詢失敗: {str(e)}'}), 500

@patent_bp.route('/report/<task_id>', methods=['GET'])
@cross_origin()
def generate_report(task_id):
    """
    生成完整的專利分析報告
    """
    try:
        if task_id not in analysis_tasks:
            return jsonify({'error': '找不到指定的分析任務'}), 404
        
        task = analysis_tasks[task_id]
        
        if task['status'] != 'completed':
            return jsonify({'error': '分析尚未完成，無法生成報告'}), 400
        
        result = task['result']
        
        # 生成詳細報告
        report_data = {
            'task_id': task_id,
            'report_title': '專利分析報告',
            'filename': task.get('filename', '未知檔案'),
            'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'executive_summary': f"本專利共識別出 {len(result['chemical_formulas'])} 個化學式和 {len(result['smiles_structures'])} 個化學結構，分析了 {result['pages_processed']} 頁內容。",
            'detailed_analysis': {
                'chemical_compounds': {
                    'formulas': result['chemical_formulas'],
                    'smiles': result['smiles_structures'],
                    'count': result['analysis_summary']['total_compounds'],
                    'types': result['analysis_summary'].get('compound_types', [])
                },
                'patent_elements': result['patent_elements'],
                'technical_analysis': {
                    'pages_analyzed': result['pages_processed'],
                    'images_extracted': result['images_extracted'],
                    'patent_strength': result['analysis_summary'].get('patent_strength', '未評估')
                }
            },
            'recommendations': [
                '建議進一步驗證化學結構的準確性',
                '考慮與現有專利進行比較分析',
                '評估商業化可行性和市場潛力'
            ]
        }
        
        return jsonify(report_data), 200
        
    except Exception as e:
        return jsonify({'error': f'報告生成失敗: {str(e)}'}), 500

