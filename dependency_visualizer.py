import sys
import re
import yaml
import subprocess
import os
import shutil
from pathlib import Path
from typing import Dict, List, Set, Tuple

try:
    subprocess.run(['dot', '-V'], check=True, capture_output=True)
    GRAPHVIZ_AVAILABLE = True
except (subprocess.CalledProcessError, FileNotFoundError):
    GRAPHVIZ_AVAILABLE = False

class DependencyVisualizer:
    def __init__(self, config_file: str):
        self.config: Dict = {}
        self.graph: Dict[str, Set[str]] = {}
        self.reverse_graph: Dict[str, Set[str]] = {}
        self.all_packages: Set[str] = set()
        self.cycles: List[List[str]] = []
        self._load_config(config_file)
        self.max_depth = int(self.config.get('max_depth', 3))
        self.filter_substring = str(self.config.get('filter_substring', '')).lower()
        
    def _load_config(self, config_file: str):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
        except FileNotFoundError:
            raise ValueError(f"Ошибка: Файл конфигурации '{config_file}' не найден.")
        except yaml.YAMLError as e:
            raise ValueError(f"Ошибка парсинга YAML в файле '{config_file}': {e}")
            
        required_keys = ['package_name', 'repository_url', 'test_mode']
        for key in required_keys:
            if key not in self.config:
                raise ValueError(f"Ошибка: В конфигурации отсутствует обязательный ключ '{key}'.")

        if str(self.config['test_mode']).lower() == 'true' and 'test_repository_path' not in self.config:
            raise ValueError("Ошибка: В тестовом режиме требуется 'test_repository_path'.")

        print("Проверка конфигурации пройдена.")
        
    def run_stage1(self):
        print("ЭТАП 1: МИНИМАЛЬНЫЙ ПРОТОТИП С КОНФИГУРАЦИЕЙ")
        print("Загруженная конфигурация:")
        for key, value in self.config.items():
            print(f"  {key}: '{value}'")
        print("Проверка конфигурации пройдена.")

    def _get_direct_dependencies_pypi(self, package_name: str) -> List[str]:
        print(f"Предупреждение: для пакета '{package_name}' архивы не найдены (Требуется реализация сетевого парсинга).")
        return []

    def _get_direct_dependencies_test(self, package_name: str) -> List[str]:
        repo_path = Path(self.config['test_repository_path'])
        
        target_path = repo_path / package_name / 'setup.py' 

        if not target_path.exists():
            return []

        content = target_path.read_text(encoding='utf-8')
        deps = []
        
        matches = re.findall(r'install_requires\s*=\s*\[(.*?)\]', content, re.DOTALL | re.IGNORECASE)
        
        for block in matches:
            pkg_names = re.findall(r'[\'"]([A-Za-z0-9_.-]+)[\'"](?:\s*(?:>=|<=|==|!=|>|<).*?)?(?=[,\]\n]|$)', block)
            deps.extend([name for name in pkg_names if name.strip()])

        return sorted(list(set(deps)))

    def get_direct_dependencies(self, package_name: str) -> List[str]:
        self.all_packages.add(package_name)
        if str(self.config['test_mode']).lower() == 'true':
            return self._get_direct_dependencies_test(package_name)
        else:
            return self._get_direct_dependencies_pypi(package_name)

    def run_stage2(self):
        print("ЭТАП 2: СБОР ДАННЫХ (прямые зависимости)")
        package_name = self.config['package_name']
        deps = self.get_direct_dependencies(package_name)
        
        if deps:
            print(f"Прямые зависимости пакета '{package_name}':")
            for i, dep in enumerate(deps, 1):
                print(f"  {i}. {dep}")
        else:
            print(f"Прямые зависимости пакета '{package_name}':\n  (нет прямых зависимостей)")

        return deps

    def _is_filtered(self, package_name: str) -> bool:
        return self.filter_substring and self.filter_substring in package_name.lower()

    def build_dependency_graph(self):
        package_name = self.config['package_name']
        self.all_packages.add(package_name)
        
        queue: List[Tuple[str, int]] = [(package_name, 0)]
        visited: Set[str] = {package_name}

        while queue:
            current_pkg, current_depth = queue.pop(0)

            if current_depth >= self.max_depth and current_pkg != package_name:
                continue

            if current_pkg == package_name and current_depth == 0:
                deps = self.get_direct_dependencies(current_pkg)
            else:
                deps = self.get_direct_dependencies(current_pkg)

            self.graph[current_pkg] = set()
            
            for dep in deps:
                if self._is_filtered(dep):
                    continue
                
                self.graph[current_pkg].add(dep)
                self.all_packages.add(dep)
                
                if dep not in visited and current_depth + 1 < self.max_depth:
                    visited.add(dep)
                    queue.append((dep, current_depth + 1))
        
        self._build_reverse_graph()
        
    def _build_reverse_graph(self):
        self.reverse_graph = {pkg: set() for pkg in self.all_packages}
        for pkg, deps in self.graph.items():
            for dep in deps:
                if dep in self.reverse_graph:
                    self.reverse_graph[dep].add(pkg)

    def _find_cycles_dfs(self, node: str, visiting: Set[str], path: List[str]):
        visiting.add(node)
        path.append(node)

        for neighbor in sorted(list(self.graph.get(node, set()))):
            if neighbor in path:
                cycle_start_index = path.index(neighbor)
                self.cycles.append(path[cycle_start_index:] + [neighbor])
            
            if neighbor in visiting:
                continue
                
            self._find_cycles_dfs(neighbor, visiting, path)

        path.pop()
        visiting.remove(node)


    def run_stage3(self):
        print("ЭТАП 3: ПОСТРОЕНИЕ ГРАФА ЗАВИСИМОСТЕЙ")
        print(f"Анализируемый пакет: {self.config['package_name']}")
        print(f"Максимальная глубина: {self.max_depth}")
        
        if self.filter_substring:
            print(f"Подстрока для фильтрации: '{self.filter_substring}'")
            
        if str(self.config['test_mode']).lower() == 'true':
            print("ТЕСТОВЫЙ РЕЖИМ (локальный репозиторий)")

        self.build_dependency_graph()
        self.cycles = []
        
        for pkg in sorted(list(self.all_packages)):
            self._find_cycles_dfs(pkg, set(), [])

        print("\nПостроенный граф:")
        for pkg, deps in self.graph.items():
            deps_list = sorted(list(deps)) if deps else ['(нет)']
            print(f"  {pkg} -> {deps_list}")

        if self.cycles:
            print(f"\nОбнаружено циклов: {len(self.cycles)}")
            for i, cycle in enumerate(self.cycles, 1):
                print(f"  Цикл {i}: {' -> '.join(cycle)}")
        else:
            print("\nЦиклические зависимости не обнаружены.")

    def topological_sort(self) -> List[str]:
        in_degree: Dict[str, int] = {pkg: 0 for pkg in self.all_packages}
        
        for pkg in self.all_packages:
            for dep in self.graph.get(pkg, set()):
                in_degree[dep] = in_degree.get(dep, 0) + 1
        
        queue = [pkg for pkg in sorted(self.all_packages) if in_degree[pkg] == 0]
        sorted_list = []
        
        while queue:
            u = queue.pop(0)
            sorted_list.append(u)
            
            for v in sorted(list(self.graph.get(u, set()))):
                in_degree[v] -= 1
                if in_degree[v] == 0:
                    queue.append(v)
                    
        cyclical_nodes = [pkg for pkg, degree in in_degree.items() if degree > 0]
        
        if cyclical_nodes:
            print(f"Предупреждение: циклические узлы исключены из порядка: {', '.join(sorted(cyclical_nodes))}")

        # Возвращаем ациклическую часть в обратном порядке (зависимости ДО пакетов)
        return [pkg for pkg in sorted_list if pkg not in cyclical_nodes][::-1]

    def _get_pipdeptree_output(self, *args):
        try:
            result = subprocess.run(['pipdeptree'] + list(args), capture_output=True, text=True, check=True)
            return result.stdout
        except (FileNotFoundError, subprocess.CalledProcessError):
            return None

    def run_stage4(self):
        print("ЭТАП 4: ПОРЯДОК ЗАГРУЗКИ (топологическая сортировка)")
        
        order = self.topological_sort()
        print("Рекомендуемый порядок установки:")
        for i, pkg in enumerate(order, 1):
            print(f"  {i}. {pkg}")

        if str(self.config['test_mode']).lower() == 'true':
            pip_output = None
        else:
            pip_output = self._get_pipdeptree_output('-p', self.config['package_name'])

        if pip_output is not None:
            pip_order = re.findall(r'([A-Za-z0-9_.-]+)', pip_output)
            print("\nСравнение с pipdeptree (только имена):")
            print(f"  Наш порядок (ациклическая часть): {', '.join(order)}")
            print(f"  pipdeptree (порядок глубины): {', '.join(pip_order)}")
            print("\nОбъяснение расхождений:")
            print("- pipdeptree использует DFS и выводит зависимости в порядке обхода (по глубине),\n  в то время как топологическая сортировка предоставляет линейный порядок, гарантирующий, что зависимости\n  будут установлены ДО пакетов, которые от них зависят.")
            print("- pipdeptree включает циклические зависимости (с предупреждением), мы их исключаем.")
        else:
            print("\npipdeptree недоступен (не установлен или ошибка).")
            
    def generate_dot_code(self) -> str:
        dot_code = [
            "digraph dependencies {",
            "  rankdir=TB;",
            "  node [shape=box, style=filled, fillcolor=\"#E0F0FF\"];"
        ]

        for pkg, deps in self.graph.items():
            for dep in deps:
                # Проверка на то, является ли это ребро частью любого цикла
                is_cyclic = any(pkg in cycle and dep in cycle for cycle in self.cycles)
                color = "red" if is_cyclic else "black"
                style = "bold" if is_cyclic else "solid"
                
                dot_code.append(f'  "{pkg}" -> "{dep}" [color="{color}", style="{style}"];')

        dot_code.append("}")
        return "\n".join(dot_code)

    def run_stage5(self):
        print("ЭТАП 5: ВИЗУАЛИЗАЦИЯ")
        dot_code = self.generate_dot_code()
        
        print("Сгенерированный DOT-код:")
        print(dot_code)
        
        dot_file_name = "graph.dot"
        with open(dot_file_name, 'w', encoding='utf-8') as f:
            f.write(dot_code)
        print(f"\nDOT-файл сохранен как {dot_file_name}.")

        if GRAPHVIZ_AVAILABLE:
            try:
                from graphviz import Source
                src = Source(dot_code, format="png")
                # Для работы, возможно, потребуется установить `python3 -m pip install graphviz`
                # и сам Graphviz (программа `dot`) в систему.
                output_path = src.render(view=True, cleanup=True)
                print(f"Граф сохранен и открыт: {output_path}")
            except Exception as e:
                print(f"Ошибка при рендеринге Graphviz: {e}. Убедитесь, что Graphviz установлен и добавлен в PATH.")
        else:
            print("Graphviz не установлен. Невозможно сгенерировать и открыть изображение.")
            
        if str(self.config['test_mode']).lower() != 'true':
            pip_graph = self._get_pipdeptree_output('--graph-output', 'dot')
            if pip_graph is not None:
                print("\nСравнение с pipdeptree --graph-output dot:")
                print("- pipdeptree включает ВСЕ зависимости (включая вложенные), мы ограничиваем по max_depth.")
                print("- pipdeptree не фильтрует по подстроке.")
                print("- pipdeptree не подсвечивает циклы цветом (но выдает предупреждения).")
            else:
                print("\npipdeptree --graph-output недоступен.")
        
    def run_stage(self, stage: str):
        if stage == '--stage1':
            self.run_stage1()
        elif stage == '--stage2':
            self.run_stage1()
            print("-" * 60)
            self.run_stage2()
        elif stage == '--stage3':
            self.run_stage1()
            print("-" * 60)
            self.run_stage3()
        elif stage == '--stage4':
            self.run_stage1()
            print("-" * 60)
            self.run_stage3()
            print("-" * 60)
            self.run_stage4()
        elif stage == '--stage5':
            self.run_stage1()
            print("-" * 60)
            self.run_stage3()
            print("-" * 60)
            self.run_stage4()
            print("-" * 60)
            self.run_stage5()
        else:
            print(f"Неизвестный этап: {stage}")

if __name__ == "__main__":
    if len(sys.argv) < 3 or not sys.argv[2].startswith('--stage'):
        print("Использование: python dependency_visualizer.py <config_file.yaml> --stageN")
        sys.exit(1)

    config_file = sys.argv[1]
    stage_to_run = sys.argv[2]
    
    try:
        # Проверка на активное виртуальное окружение
        if not 'VIRTUAL_ENV' in os.environ and stage_to_run in ('--stage4', '--stage5'):
            print("!!! ПРЕДУПРЕЖДЕНИЕ: Виртуальное окружение не активно. Используйте .venv для изоляции.")
        
        # Проверка Graphviz
        if not GRAPHVIZ_AVAILABLE and stage_to_run == '--stage5':
            print("!!! ОШИБКА: Graphviz (инструмент 'dot') не найден. Визуализация невозможна. Установите Graphviz.")
            
        app = DependencyVisualizer(config_file)
        print("============================================================")
        app.run_stage(stage_to_run)
        print("\nЭтап успешно завершен.")

    except ValueError as e:
        print(f"Критическая ошибка: {e}")
        sys.exit(1)