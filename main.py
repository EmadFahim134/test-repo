import os
import sys
import subprocess
import json
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QListWidget, QPushButton, QLabel, QLineEdit, QComboBox, 
                            QMessageBox, QStackedWidget, QProgressBar)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QIcon, QPalette, QColor
import requests
import tempfile
import shutil
import win32com.client  # For Windows shortcuts (pip install pywin32)

class GitHubAPI(QThread):
    search_complete = pyqtSignal(list)
    
    def __init__(self, query):
        super().__init__()
        self.query = query
        
    def run(self):
        try:
            url = f"https://api.github.com/search/repositories?q={self.query}+language:python&sort=stars&order=desc"
            response = requests.get(url)
            if response.status_code == 200:
                results = []
                for item in response.json()['items']:
                    if item['description'] is None:
                        item['description'] = "No description available"
                    results.append({
                        'name': item['name'],
                        'full_name': item['full_name'],
                        'description': item['description'],
                        'html_url': item['html_url'],
                        'clone_url': item['clone_url'],
                        'stars': item['stargazers_count']
                    })
                self.search_complete.emit(results)
        except Exception as e:
            print(f"Error fetching GitHub data: {e}")
            self.search_complete.emit([])

class InstallThread(QThread):
    progress_update = pyqtSignal(int, str)
    install_complete = pyqtSignal(bool, str)
    
    def __init__(self, repo_data, install_path):
        super().__init__()
        self.repo_data = repo_data
        self.install_path = install_path
        
    def run(self):
        try:
            # Step 1: Clone repository
            self.progress_update.emit(10, "Cloning repository...")
            clone_dir = os.path.join(self.install_path, self.repo_data['name'])
            
            if os.path.exists(clone_dir):
                shutil.rmtree(clone_dir)
                
            subprocess.run(['git', 'clone', self.repo_data['clone_url']], 
                          cwd=self.install_path, 
                          check=True)
            
            # Step 2: Create shortcut (Windows specific)
            self.progress_update.emit(60, "Creating shortcut...")
            self.create_shortcut(clone_dir)
            
            self.progress_update.emit(100, "Installation complete!")
            self.install_complete.emit(True, f"Successfully installed {self.repo_data['name']}")
            
        except Exception as e:
            self.install_complete.emit(False, f"Installation failed: {str(e)}")
    
    def create_shortcut(self, target_dir):
        """Create Windows shortcut in Start Menu"""
        start_menu = os.path.join(os.environ['APPDATA'], 'Microsoft', 'Windows', 'Start Menu', 'Programs')
        shortcut_path = os.path.join(start_menu, f"{self.repo_data['name']}.lnk")
        
        # Find main Python file (simplified - would need better detection in real app)
        main_py = os.path.join(target_dir, 'main.py')
        if not os.path.exists(main_py):
            # Look for any .py file
            for file in os.listdir(target_dir):
                if file.endswith('.py'):
                    main_py = os.path.join(target_dir, file)
                    break
        
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(shortcut_path)
        shortcut.TargetPath = sys.executable  # Python executable
        shortcut.Arguments = f'"{main_py}"'
        shortcut.WorkingDirectory = target_dir
        shortcut.IconLocation = sys.executable  # Use Python icon as default
        shortcut.save()

class PythonAppStore(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Python App Store - Beta")
        self.setGeometry(100, 100, 800, 600)
        self.install_path = os.path.join(tempfile.gettempdir(), "PythonAppStore")  # Temp dir for demo
        
        # Create install directory if it doesn't exist
        if not os.path.exists(self.install_path):
            os.makedirs(self.install_path)
        
        self.dark_mode = True
        self.current_repo = None
        
        self.init_ui()
        self.apply_theme()
        
    def init_ui(self):
        # Central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.main_layout = QVBoxLayout(central_widget)
        
        # Header
        header = QHBoxLayout()
        self.title = QLabel("Python App Store")
        self.title.setStyleSheet("font-size: 24px; font-weight: bold;")
        header.addWidget(self.title)
        
        self.theme_toggle = QPushButton("Toggle Theme")
        self.theme_toggle.clicked.connect(self.toggle_theme)
        header.addWidget(self.theme_toggle)
        
        self.main_layout.addLayout(header)
        
        # Search bar
        search_layout = QHBoxLayout()
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search Python projects on GitHub...")
        self.search_bar.returnPressed.connect(self.search_repos)
        search_layout.addWidget(self.search_bar)
        
        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self.search_repos)
        search_layout.addWidget(self.search_btn)
        
        self.main_layout.addLayout(search_layout)
        
        # Content area
        self.content_stack = QStackedWidget()
        
        # Search results page
        self.results_page = QWidget()
        results_layout = QVBoxLayout(self.results_page)
        
        self.results_list = QListWidget()
        self.results_list.itemClicked.connect(self.show_repo_details)
        results_layout.addWidget(self.results_list)
        
        self.content_stack.addWidget(self.results_page)
        
        # Details page
        self.details_page = QWidget()
        details_layout = QVBoxLayout(self.details_page)
        
        self.repo_name = QLabel()
        self.repo_name.setStyleSheet("font-size: 18px; font-weight: bold;")
        details_layout.addWidget(self.repo_name)
        
        self.repo_desc = QLabel()
        self.repo_desc.setWordWrap(True)
        details_layout.addWidget(self.repo_desc)
        
        self.repo_stats = QLabel()
        details_layout.addWidget(self.repo_stats)
        
        self.install_btn = QPushButton("Install")
        self.install_btn.clicked.connect(self.install_repo)
        details_layout.addWidget(self.install_btn)
        
        self.back_btn = QPushButton("Back to Search")
        self.back_btn.clicked.connect(lambda: self.content_stack.setCurrentIndex(0))
        details_layout.addWidget(self.back_btn)
        
        self.content_stack.addWidget(self.details_page)
        
        # Installation progress page
        self.progress_page = QWidget()
        progress_layout = QVBoxLayout(self.progress_page)
        
        self.progress_label = QLabel("Installing...")
        progress_layout.addWidget(self.progress_label)
        
        self.progress_bar = QProgressBar()
        progress_layout.addWidget(self.progress_bar)
        
        self.content_stack.addWidget(self.progress_page)
        
        self.main_layout.addWidget(self.content_stack)
        
    def apply_theme(self):
        palette = QPalette()
        
        if self.dark_mode:
            palette.setColor(QPalette.Window, QColor(53, 53, 53))
            palette.setColor(QPalette.WindowText, Qt.white)
            palette.setColor(QPalette.Base, QColor(25, 25, 25))
            palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
            palette.setColor(QPalette.ToolTipBase, Qt.white)
            palette.setColor(QPalette.ToolTipText, Qt.white)
            palette.setColor(QPalette.Text, Qt.white)
            palette.setColor(QPalette.Button, QColor(53, 53, 53))
            palette.setColor(QPalette.ButtonText, Qt.white)
            palette.setColor(QPalette.BrightText, Qt.red)
            palette.setColor(QPalette.Link, QColor(42, 130, 218))
            palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
            palette.setColor(QPalette.HighlightedText, Qt.black)
        else:
            palette.setColor(QPalette.Window, Qt.white)
            palette.setColor(QPalette.WindowText, Qt.black)
            palette.setColor(QPalette.Base, Qt.white)
            palette.setColor(QPalette.AlternateBase, QColor(240, 240, 240))
            palette.setColor(QPalette.ToolTipBase, Qt.white)
            palette.setColor(QPalette.ToolTipText, Qt.black)
            palette.setColor(QPalette.Text, Qt.black)
            palette.setColor(QPalette.Button, QColor(240, 240, 240))
            palette.setColor(QPalette.ButtonText, Qt.black)
            palette.setColor(QPalette.BrightText, Qt.red)
            palette.setColor(QPalette.Link, QColor(0, 0, 255))
            palette.setColor(QPalette.Highlight, QColor(0, 0, 255))
            palette.setColor(QPalette.HighlightedText, Qt.white)
        
        self.setPalette(palette)
        
    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self.apply_theme()
        
    def search_repos(self):
        query = self.search_bar.text()
        if not query:
            QMessageBox.warning(self, "Warning", "Please enter a search term")
            return
            
        self.search_bar.setEnabled(False)
        self.search_btn.setEnabled(False)
        
        self.api_thread = GitHubAPI(query)
        self.api_thread.search_complete.connect(self.display_results)
        self.api_thread.start()
        
    def display_results(self, results):
        self.search_bar.setEnabled(True)
        self.search_btn.setEnabled(True)
        
        self.results_list.clear()
        
        if not results:
            QMessageBox.information(self, "No Results", "No repositories found matching your search.")
            return
            
        for repo in results:
            item_text = f"{repo['full_name']} - ★{repo['stars']}\n{repo['description']}"
            self.results_list.addItem(item_text)
            self.results_list.item(self.results_list.count()-1).setData(Qt.UserRole, repo)
            
    def show_repo_details(self, item):
        self.current_repo = item.data(Qt.UserRole)
        
        self.repo_name.setText(self.current_repo['full_name'])
        self.repo_desc.setText(self.current_repo['description'])
        self.repo_stats.setText(f"Stars: {self.current_repo['stars']}\nURL: {self.current_repo['html_url']}")
        
        self.content_stack.setCurrentIndex(1)
        
    def install_repo(self):
        if not self.current_repo:
            return
            
        reply = QMessageBox.question(
            self, 
            "Confirm Installation", 
            f"Install {self.current_repo['full_name']} to your Start Menu?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.content_stack.setCurrentIndex(2)
            
            self.install_thread = InstallThread(self.current_repo, self.install_path)
            self.install_thread.progress_update.connect(self.update_progress)
            self.install_thread.install_complete.connect(self.install_finished)
            self.install_thread.start()
            
    def update_progress(self, value, message):
        self.progress_bar.setValue(value)
        self.progress_label.setText(message)
        
    def install_finished(self, success, message):
        if success:
            QMessageBox.information(self, "Success", message)
        else:
            QMessageBox.warning(self, "Error", message)
            
        self.content_stack.setCurrentIndex(0)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Set application style
    app.setStyle('Fusion')
    
    window = PythonAppStore()
    window.show()
    
    sys.exit(app.exec_())