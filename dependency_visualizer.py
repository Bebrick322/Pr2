#!/usr/bin/env python3
import yaml
import sys
import os
import re
import urllib.request
from typing import Dict, Any, List, Set, Optional


class DependencyVisualizer:
    def __init__(self):
        self.config: Dict[str, Any] = {}
        self.default_config = {
            'package_name': 'requests',
            'repository_url': 'https://pypi.org/simple/',
            'test_repository_path': './test_repo',
            'test_mode': False,
            'max_depth': 3,
            'filter_substring': ''
        }
        self.config = self.default_config.copy()

    def load_config(self, config_path: str) -> bool:
        try:
            if not os.path.isfile(config_path):
                raise FileNotFoundError(f"Конфигурационный файл не найден: {config_path}")
            if not config_path.endswith(('.yaml', '.yml')):
                raise ValueError("Файл конфигурации должен иметь расширение .yaml или .yml")
            with open(config_path, 'r', encoding='utf-8') as f:
                loaded = yaml.safe_load(f)
            if loaded is None:
                raise ValueError("Файл конфигурации пуст или содержит неверный YAML")
            self._validate_and_apply_config(loaded)
            return True
        except Exception as e:
            print(f"[Ошибка конфигурации] {e}")
            return False

    def _validate_and_apply_config(self, cfg: Dict[str, Any]):
        c = self.default_config.copy()
        name = cfg.get('package_name', '').strip()
        if not name:
            raise ValueError("package_name не может быть пустым")
        c['package_name'] = name
        url = cfg.get('repository_url', '')
        if url and not (url.startswith('http://') or url.startswith('https://')):
            raise ValueError("repository_url должен начинаться с http:// или https://")
        c['repository_url'] = url
        path = cfg.get('test_repository_path', './test_repo')
        c['test_repository_path'] = path
        test_mode = cfg.get('test_mode', False)
        if not isinstance(test_mode, bool):
            raise ValueError("test_mode должен быть булевым значением")
        c['test_mode'] = test_mode
        depth = cfg.get('max_depth', 3)
        if not isinstance(depth, int) or depth < 1 or depth > 10:
            raise ValueError("max_depth должен быть целым числом от 1 до 10")
        c['max_depth'] = depth
        flt = cfg.get('filter_substring', '')
        if not isinstance(flt, str):
            raise ValueError("filter_substring должен быть строкой")
        c['filter_substring'] = flt
        self.config = c

    def print_config(self):
        print("=" * 60)
        print("ТЕКУЩАЯ КОНФИГУРАЦИЯ:")
        for k, v in self.config.items():
            print(f"{k}: {v}")
        print("=" * 60)

    def fetch_package_page(self, pkg: str) -> Optional[str]:
        url = f"{self.config['repository_url'].rstrip('/')}/{pkg}/"
        try:
            headers = {'User-Agent': 'DepVisualizer/1.0'}
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as r:
                if r.status == 200:
                    return r.read().decode('utf-8')
        except Exception as e:
            print(f"Ошибка загрузки {pkg}: {e}")
        return None

    def extract_dependencies_from_html(self, html: str) -> List[str]:
        deps = set()
        patterns = [r'Requires:\s*([A-Za-z0-9_\-,\s]+)', r'install_requires\s*=\s*\[(.*?)\]']
        for pat in patterns:
            for match in re.findall(pat, html, re.DOTALL | re.IGNORECASE):
                names = re.findall(r'[A-Za-z0-9_\-]+', match)
                deps.update(names)
        return sorted(deps)

    def analyze_test_graph(self, path: str) -> Dict[str, List[str]]:
        graph: Dict[str, List[str]] = {}
        if not os.path.exists(path):
            raise FileNotFoundError(f"Файл тестового графа не найден: {path}")
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                if ':' not in line:
                    continue
                pkg, deps = line.strip().split(':', 1)
                deps_list = [d.strip() for d in deps.split(',') if d.strip()]
                graph[pkg.strip()] = deps_list
        return graph

    def get_direct_dependencies(self, pkg: str) -> List[str]:
        if self.config['test_mode']:
            test_file = self.config['test_repository_path']
            graph = self.analyze_test_graph(test_file)
            return graph.get(pkg, [])
        html = self.fetch_package_page(pkg)
        if not html:
            return []
        deps = self.extract_dependencies_from_html(html)
        flt = self.config['filter_substring'].lower()
        if flt:
            deps = [d for d in deps if flt not in d.lower()]
        return deps

    def print_dependencies(self, deps: List[str]):
        print("=" * 60)
        print(f"Прямые зависимости пакета '{self.config['package_name']}':")
        if deps:
            for d in deps:
                print(f" - {d}")
        else:
            print("(не найдены)")
        print("=" * 60)

    def build_dependency_graph(self, pkg: str, depth=0, visited=None) -> Dict[str, List[str]]:
        if visited is None:
            visited = set()
        if depth > self.config['max_depth']:
            return {}
        if pkg in visited:
            return {}
        visited.add(pkg)
        deps = self.get_direct_dependencies(pkg)
        graph = {pkg: deps}
        for dep in deps:
            sub = self.build_dependency_graph(dep, depth + 1, visited)
            graph.update(sub)
        return graph

    def print_graph(self, graph: Dict[str, List[str]]):
        print("=" * 60)
        print("ГРАФ ЗАВИСИМОСТЕЙ:")
        for k, v in graph.items():
            print(f"{k} -> {', '.join(v) if v else '(нет зависимостей)'}")
        print("=" * 60)

    def compute_load_order(self, graph: Dict[str, List[str]]) -> List[str]:
        visited, order = set(), []
        def dfs(node):
            if node in visited:
                return
            visited.add(node)
            for dep in graph.get(node, []):
                dfs(dep)
            order.append(node)
        for n in graph:
            dfs(n)
        return list(reversed(order))

    def export_to_graphviz(self, graph: Dict[str, List[str]], outfile="graph.dot"):
        with open(outfile, 'w', encoding='utf-8') as f:
            f.write("digraph dependencies {\n")
            for pkg, deps in graph.items():
                for dep in deps:
                    f.write(f'    "{pkg}" -> "{dep}";\n')
            f.write("}\n")
        print(f"Граф сохранён в файл: {outfile}")

    def run_stage1(self):
        print("\n=== ЭТАП 1: КОНФИГУРАЦИЯ ===")
        self.print_config()
        print("Конфигурация успешно загружена и проверена.\n")

    def run_stage2(self):
        print("\n=== ЭТАП 2: СБОР ДАННЫХ ===")
        deps = self.get_direct_dependencies(self.config['package_name'])
        self.print_dependencies(deps)

    def run_stage3(self):
        print("\n=== ЭТАП 3: ПОСТРОЕНИЕ ГРАФА ===")
        graph = self.build_dependency_graph(self.config['package_name'])
        self.print_graph(graph)
        return graph

    def run_stage4(self, graph: Dict[str, List[str]]):
        print("\n=== ЭТАП 4: ПОРЯДОК ЗАГРУЗКИ ===")
        order = self.compute_load_order(graph)
        print("Порядок загрузки зависимостей:")
        for i, pkg in enumerate(order, 1):
            print(f"{i}. {pkg}")
        return order

    def run_stage5(self, graph: Dict[str, List[str]]):
        print("\n=== ЭТАП 5: ВИЗУАЛИЗАЦИЯ ===")
        self.export_to_graphviz(graph)
        print("Файл .dot можно визуализировать через Graphviz: dot -Tpng graph.dot -o graph.png")

    def run_cli(self):
        if len(sys.argv) < 3:
            print("Использование:")
            print("  python dependency_visualizer.py <config.yaml> --stageN")
            sys.exit(1)
        config_file = sys.argv[1]
        stage = sys.argv[2]
        if not self.load_config(config_file):
            sys.exit(1)
        if stage == "--stage1":
            self.run_stage1()
        elif stage == "--stage2":
            self.run_stage2()
        elif stage == "--stage3":
            graph = self.run_stage3()
        elif stage == "--stage4":
            graph = self.run_stage3()
            self.run_stage4(graph)
        elif stage == "--stage5":
            graph = self.run_stage3()
            self.run_stage5(graph)
        else:
            print(f"Неизвестный этап: {stage}")


if __name__ == "__main__":
    visualizer = DependencyVisualizer()
    visualizer.run_cli()
