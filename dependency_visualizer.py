#!/usr/bin/env python3
"""
Инструмент визуализации графа зависимостей пакетов
Этапы 1-2: Конфигурация и сбор данных
"""

import yaml
import sys
import os
import re
import urllib.request
import urllib.error
from typing import Dict, Any, List, Set, Optional
from pathlib import Path


class DependencyVisualizer:
    def __init__(self):
        self.config: Dict[str, Any] = {}
        self.default_config = {
            'package_name': 'requests',  # Установлено значение по умолчанию
            'repository_url': 'https://pypi.org/simple/',
            'test_repository_path': './test_repo',
            'test_mode': False,
            'max_depth': 3,
            'filter_substring': ''
        }
        # Инициализируем конфигурацию значениями по умолчанию
        self.config = self.default_config.copy()
        self.command_history: List[str] = []
    
    def load_config(self, config_path: str) -> bool:
        """Загружает конфигурацию из YAML файла"""
        try:
            # Проверка существования файла
            if not os.path.isfile(config_path):
                raise FileNotFoundError(f"Конфигурационный файл не найден: {config_path}")
            
            # Проверка расширения файла
            if not config_path.lower().endswith(('.yaml', '.yml')):
                raise ValueError(f"Неверное расширение файла: {config_path}. Ожидается .yaml или .yml")
            
            # Чтение файла
            with open(config_path, 'r', encoding='utf-8') as f:
                loaded_config = yaml.safe_load(f)
            
            if loaded_config is None:
                raise ValueError("Конфигурационный файл пуст или содержит неверный YAML")
            
            # Валидация и применение конфигурации
            self._validate_and_apply_config(loaded_config)
            return True
            
        except yaml.YAMLError as e:
            print(f"Ошибка синтаксиса YAML: {e}")
            return False
        except Exception as e:
            print(f"Ошибка загрузки конфигурации: {e}")
            return False
    
    def _validate_and_apply_config(self, loaded_config: Dict[str, Any]) -> None:
        """Валидирует и применяет загруженную конфигурацию"""
        # Сохраняем текущую конфигурацию как основу
        current_config = self.config.copy()
        
        # Валидация package_name
        if 'package_name' in loaded_config:
            package_name = loaded_config['package_name']
            if not isinstance(package_name, str):
                raise ValueError("package_name должен быть строкой")
            if not package_name.strip():
                raise ValueError("package_name не может быть пустым")
            current_config['package_name'] = package_name.strip()
        
        # Валидация repository_url
        if 'repository_url' in loaded_config:
            repo_url = loaded_config['repository_url']
            if not isinstance(repo_url, str):
                raise ValueError("repository_url должен быть строкой")
            if repo_url and not (repo_url.startswith('http://') or repo_url.startswith('https://')):
                raise ValueError("repository_url должен начинаться с http:// или https://")
            current_config['repository_url'] = repo_url
        
        # Валидация test_repository_path
        if 'test_repository_path' in loaded_config:
            test_path = loaded_config['test_repository_path']
            if not isinstance(test_path, str):
                raise ValueError("test_repository_path должен быть строкой")
            if test_path and not os.path.exists(test_path):
                raise ValueError(f"test_repository_path не существует: {test_path}")
            current_config['test_repository_path'] = test_path
        
        # Валидация test_mode
        if 'test_mode' in loaded_config:
            test_mode = loaded_config['test_mode']
            if not isinstance(test_mode, bool):
                raise ValueError("test_mode должен быть булевым значением")
            current_config['test_mode'] = test_mode
        
        # Валидация max_depth
        if 'max_depth' in loaded_config:
            max_depth = loaded_config['max_depth']
            if not isinstance(max_depth, int):
                raise ValueError("max_depth должен быть целым числом")
            if max_depth < 1:
                raise ValueError("max_depth должен быть положительным числом")
            if max_depth > 10:
                raise ValueError("max_depth не может превышать 10")
            current_config['max_depth'] = max_depth
        
        # Валидация filter_substring
        if 'filter_substring' in loaded_config:
            filter_str = loaded_config['filter_substring']
            if not isinstance(filter_str, str):
                raise ValueError("filter_substring должен быть строкой")
            current_config['filter_substring'] = filter_str
        
        # Дополнительная валидация логики
        if current_config['test_mode'] and not current_config['test_repository_path']:
            raise ValueError("В режиме test_mode должен быть указан test_repository_path")
        
        if not current_config['test_mode'] and not current_config['repository_url']:
            raise ValueError("В обычном режиме должен быть указан repository_url")
        
        # Применяем валидированную конфигурацию
        self.config = current_config
    
    def print_config(self) -> None:
        """Выводит все параметры конфигурации в формате ключ-значение"""
        print("=" * 50)
        print("НАСТРОЙКИ ПОЛЬЗОВАТЕЛЯ")
        print("=" * 50)
        
        for key, value in self.config.items():
            print(f"{key}: {value}")
        
        print("=" * 50)
    
    def extract_dependencies_from_html(self, html_content: str) -> List[str]:
        """Извлекает зависимости из HTML страницы пакета PyPI"""
        dependencies = []
        
        # Поиск секции с зависимостями в HTML
        patterns = [
            r'<div id="dependencies"[^>]*>(.*?)</div>',
            r'Requires Distributions:</h3>(.*?)</div>',
            r'install_requires\s*=\s*\[(.*?)\]',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, html_content, re.DOTALL | re.IGNORECASE)
            for match in matches:
                # Извлечение названий пакетов из найденного текста
                package_matches = re.findall(r'[\'"]([a-zA-Z0-9_-]+)[\'"]', match)
                dependencies.extend(package_matches)
        
        # Удаление дубликатов и сортировка
        return sorted(list(set(dependencies)))
    
    def parse_requires_dist(self, html_content: str) -> List[str]:
        """Парсит зависимости из метаданных requires_dist"""
        dependencies = []
        
        # Поиск данных о зависимостях в JSON-LD или других метаданных
        json_ld_pattern = r'<script type="application/ld\+json">(.*?)</script>'
        json_matches = re.findall(json_ld_pattern, html_content, re.DOTALL)
        
        for json_str in json_matches:
            # Упрощенный поиск requires_dist в JSON
            requires_matches = re.findall(r'"requires_dist"\s*:\s*\[(.*?)\]', json_str)
            for requires_str in requires_matches:
                package_matches = re.findall(r'"([a-zA-Z0-9_-]+)(?:[^"]*)"', requires_str)
                dependencies.extend(package_matches)
        
        return sorted(list(set(dependencies)))
    
    def fetch_package_page(self, package_name: str) -> Optional[str]:
        """Получает HTML страницу пакета с PyPI"""
        url = f"{self.config['repository_url'].rstrip('/')}/{package_name}/"
        
        try:
            print(f"Получение информации о пакете: {package_name}")
            headers = {
                'User-Agent': 'DependencyVisualizer/1.0'
            }
            request = urllib.request.Request(url, headers=headers)
            
            with urllib.request.urlopen(request, timeout=10) as response:
                if response.status == 200:
                    return response.read().decode('utf-8')
                else:
                    print(f"Ошибка HTTP {response.status} для пакета {package_name}")
                    return None
                    
        except urllib.error.HTTPError as e:
            print(f"HTTP ошибка для {package_name}: {e.code} {e.reason}")
        except urllib.error.URLError as e:
            print(f"Ошибка URL для {package_name}: {e.reason}")
        except Exception as e:
            print(f"Неожиданная ошибка при получении {package_name}: {e}")
        
        return None
    
    def analyze_test_repository(self, package_name: str) -> List[str]:
        """Анализирует зависимости в тестовом репозитории"""
        dependencies = []
        repo_path = Path(self.config['test_repository_path'])
        
        # Поиск файлов setup.py
        setup_files = list(repo_path.rglob('setup.py'))
        for setup_file in setup_files:
            try:
                with open(setup_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Поиск install_requires в setup.py
                requires_matches = re.findall(
                    r'install_requires\s*=\s*\[(.*?)\]', 
                    content, 
                    re.DOTALL
                )
                
                for match in requires_matches:
                    package_matches = re.findall(r'[\'"]([a-zA-Z0-9_-]+)[\'"]', match)
                    dependencies.extend(package_matches)
                    
            except Exception as e:
                print(f"Ошибка чтения {setup_file}: {e}")
        
        return sorted(list(set(dependencies)))
    
    def get_direct_dependencies(self, package_name: str) -> List[str]:
        """Получает прямые зависимости пакета"""
        if not package_name:
            print("Ошибка: имя пакета не указано")
            return []
            
        if self.config['test_mode']:
            return self.analyze_test_repository(package_name)
        else:
            html_content = self.fetch_package_page(package_name)
            if html_content:
                # Пробуем разные методы извлечения зависимостей
                deps1 = self.extract_dependencies_from_html(html_content)
                deps2 = self.parse_requires_dist(html_content)
                
                # Объединяем результаты
                all_deps = list(set(deps1 + deps2))
                
                # Применяем фильтр если задан
                if self.config['filter_substring']:
                    all_deps = [
                        dep for dep in all_deps 
                        if self.config['filter_substring'].lower() in dep.lower()
                    ]
                
                return all_deps
            return []
    
    def print_dependencies(self, dependencies: List[str]) -> None:
        """Выводит зависимости в удобочитаемом формате"""
        if not dependencies:
            print("Прямые зависимости не найдены")
            return
        
        print("=" * 50)
        print(f"ПРЯМЫЕ ЗАВИСИМОСТИ ПАКЕТА: {self.config['package_name']}")
        print("=" * 50)
        
        for i, dep in enumerate(dependencies, 1):
            print(f"{i:2d}. {dep}")
        
        print("=" * 50)
        print(f"Всего найдено зависимостей: {len(dependencies)}")
    
    def run_stage1(self) -> None:
        """Запуск этапа 1: Вывод конфигурации"""
        print("=" * 60)
        print("ЭТАП 1: МИНИМАЛЬНЫЙ ПРОТОТИП С КОНФИГУРАЦИЕЙ")
        print("=" * 60)
        
        # Вывод конфигурации
        self.print_config()
        print("\nКонфигурация успешно загружена! Готов к анализу зависимостей.")
    
    def run_stage2(self) -> None:
        """Запуск этапа 2: Сбор данных о зависимостях"""
        print("\n" + "=" * 60)
        print("ЭТАП 2: СБОР ДАННЫХ О ЗАВИСИМОСТЯХ")
        print("=" * 60)
        
        # Проверяем, что имя пакета установлено
        if not self.config['package_name']:
            print("Ошибка: имя пакета не указано в конфигурации")
            return
        
        # Анализ зависимостей
        dependencies = self.get_direct_dependencies(self.config['package_name'])
        
        # Вывод результатов
        self.print_dependencies(dependencies)
    
    def run_interactive(self) -> None:
        """Интерактивный режим работы"""
        print("Инструмент визуализации графа зависимостей")
        print("Режим: Интерактивный")
        print()
        
        # Убеждаемся, что конфигурация инициализирована
        if not self.config:
            self.config = self.default_config.copy()
        
        while True:
            print("\nДоступные команды:")
            print("1 - Показать конфигурацию (Этап 1)")
            print("2 - Анализ зависимостей (Этап 2)")
            print("3 - Сменить пакет для анализа")
            print("4 - Включить/выключить тестовый режим")
            print("5 - Изменить глубину анализа")
            print("6 - Установить фильтр пакетов")
            print("7 - Загрузить конфигурацию из файла")
            print("0 - Выход")
            
            choice = input("\nВыберите команду: ").strip()
            
            if choice == '1':
                self.run_stage1()
            elif choice == '2':
                self.run_stage2()
            elif choice == '3':
                new_package = input("Введите имя пакета: ").strip()
                if new_package:
                    self.config['package_name'] = new_package
                    print(f"Пакет изменен на: {new_package}")
                else:
                    print("Имя пакета не может быть пустым")
            elif choice == '4':
                self.config['test_mode'] = not self.config['test_mode']
                mode = "тестовый" if self.config['test_mode'] else "боевой"
                print(f"Режим изменен на: {mode}")
                if self.config['test_mode']:
                    print("Убедитесь, что test_repository_path указан корректно")
            elif choice == '5':
                try:
                    new_depth = int(input("Введите новую глубину анализа (1-10): "))
                    if 1 <= new_depth <= 10:
                        self.config['max_depth'] = new_depth
                        print(f"Глубина анализа установлена: {new_depth}")
                    else:
                        print("Глубина должна быть от 1 до 10")
                except ValueError:
                    print("Неверный формат числа")
            elif choice == '6':
                new_filter = input("Введите подстроку для фильтрации (или Enter для очистки): ").strip()
                self.config['filter_substring'] = new_filter
                if new_filter:
                    print(f"Фильтр установлен: '{new_filter}'")
                else:
                    print("Фильтр очищен")
            elif choice == '7':
                config_file = input("Введите путь к конфигурационному файлу: ").strip()
                if config_file and self.load_config(config_file):
                    print("Конфигурация успешно загружена")
                else:
                    print("Не удалось загрузить конфигурацию")
            elif choice == '0':
                print("Выход из программы")
                break
            else:
                print("Неверная команда")
    
    def run_cli(self) -> None:
        """Режим командной строки"""
        if len(sys.argv) != 2:
            print("Использование:")
            print("  python dependency_visualizer.py <config_file.yaml>  # CLI режим")
            print("  python dependency_visualizer.py --interactive       # Интерактивный режим")
            sys.exit(1)
        
        config_file = sys.argv[1]
        
        if config_file == "--interactive":
            self.run_interactive()
            return
        
        # Загрузка конфигурации
        if not self.load_config(config_file):
            print("Не удалось загрузить конфигурацию. Проверьте файл и попробуйте снова.")
            sys.exit(1)
        
        # Запуск обоих этапов
        self.run_stage1()
        self.run_stage2()


def create_sample_config() -> None:
    """Создает пример конфигурационного файла"""
    sample_config = {
        'package_name': 'requests',
        'repository_url': 'https://pypi.org/simple/',
        'test_repository_path': './test_repo',
        'test_mode': False,
        'max_depth': 3,
        'filter_substring': ''
    }
    
    with open('config_sample.yaml', 'w', encoding='utf-8') as f:
        yaml.dump(sample_config, f, default_flow_style=False, allow_unicode=True, indent=2)
    
    print("Создан пример конфигурационного файла: config_sample.yaml")


def create_test_repository() -> None:
    """Создает тестовый репозиторий для демонстрации"""
    repo_path = Path("test_repo")
    repo_path.mkdir(exist_ok=True)
    
    # Создаем setup.py для тестового пакета
    setup_content = '''from setuptools import setup, find_packages

setup(
    name="test_package",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "requests",
        "numpy",
        "pandas",
        "matplotlib"
    ],
    extras_require={
        'dev': [
            'pytest',
            'black'
        ]
    }
)
'''
    
    with open(repo_path / "setup.py", "w") as f:
        f.write(setup_content)
    
    print("Создан тестовый репозиторий: test_repo/")


if __name__ == "__main__":
    # Создание необходимых файлов при первом запуске
    if not os.path.exists('config_sample.yaml'):
        create_sample_config()
    
    if not os.path.exists('test_repo'):
        create_test_repository()
    
    # Запуск приложения
    visualizer = DependencyVisualizer()
    
    if len(sys.argv) == 1:
        # Если аргументов нет, показываем справку
        print("Инструмент визуализации графа зависимостей")
        print("\nИспользование:")
        print("  python dependency_visualizer.py <config_file.yaml>  # CLI режим")
        print("  python dependency_visualizer.py --interactive       # Интерактивный режим")
        print("\nПримеры:")
        print("  python dependency_visualizer.py config_sample.yaml")
        print("  python dependency_visualizer.py --interactive")
        print("\nДля начала работы рекомендуется:")
        print("  python dependency_visualizer.py --interactive")
    else:
        visualizer.run_cli()