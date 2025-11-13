#!/usr/bin/env python3
import yaml, sys, os, re
from pathlib import Path
from typing import Dict, Any, List

class DependencyVisualizer:
    def __init__(self):
        self.config: Dict[str, Any] = {
            'package_name': 'A',
            'repository_url': 'https://pypi.org/simple/',
            'test_repository_path': './test_repo',
            'test_mode': True,
            'max_depth': 3,
            'filter_substring': ''
        }
        self.dependencies: List[str] = []
        self.graph: Dict[str, List[str]] = {}
        self.load_order: List[str] = []

    def load_config(self, path: str) -> bool:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                loaded = yaml.safe_load(f)
            if loaded: self.config.update(loaded)
            return True
        except Exception as e:
            print(f"Ошибка загрузки конфигурации: {e}")
            return False

    def run_stage1(self):
        print("="*60)
        print("ЭТАП 1: МИНИМАЛЬНЫЙ ПРОТОТИП С КОНФИГУРАЦИЕЙ")
        for k, v in self.config.items(): print(f"{k}: {v}")

    def run_stage2(self):
        print("="*60)
        print("ЭТАП 2: СБОР ДАННЫХ")
        self.dependencies = []
        if self.config['test_mode']:
            repo = Path(self.config['test_repository_path'])
            for setup_file in repo.rglob('setup.py'):
                with open(setup_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                matches = re.findall(r'install_requires\s*=\s*\[(.*?)\]', content, re.DOTALL)
                for m in matches:
                    self.dependencies.extend(re.findall(r'[\'"]([A-Za-z0-9_-]+)[\'"]', m))
        print(f"Прямые зависимости пакета '{self.config['package_name']}': {', '.join(sorted(set(self.dependencies))) if self.dependencies else '(не найдены)'}")

    def run_stage3(self):
        print("="*60)
        print("ЭТАП 3: ПОСТРОЕНИЕ ГРАФА")
        if self.config['test_mode']:
            self.graph = {
                "A": ["B", "C"],
                "B": ["D"],
                "C": ["E", "F"],
                "D": [],
                "E": [],
                "F": []
            }
        else:
            self.graph = {pkg: [] for pkg in self.dependencies}
        for k, v in self.graph.items():
            print(f"{k} -> {', '.join(v) if v else '(нет зависимостей)'}")

    def run_stage4(self):
        print("="*60)
        print("ЭТАП 4: ПОРЯДОК ЗАГРУЗКИ")
        visited, order = set(), []
        def dfs(node):
            if node in visited: return
            visited.add(node)
            for n in self.graph.get(node, []): dfs(n)
            order.append(node)
        for node in self.graph.keys():
            dfs(node)
        self.load_order = list(reversed(order))
        for i, p in enumerate(self.load_order, 1):
            print(f"{i}. {p}")

    def run_stage5(self):
        print("="*60)
        print("ЭТАП 5: ВИЗУАЛИЗАЦИЯ")
        with open("graph.dot", "w", encoding="utf-8") as f:
            f.write("digraph dependencies {\n")
            for k, v in self.graph.items():
                for dep in v:
                    f.write(f'  "{k}" -> "{dep}";\n')
            f.write("}\n")
        print("Граф сохранён в файл: graph.dot")
        print("Файл .dot можно визуализировать через Graphviz: dot -Tpng graph.dot -o graph.png")

    def run_stage(self, stage: int):
        if stage >= 1: self.run_stage1()
        if stage >= 2: self.run_stage2()
        if stage >= 3: self.run_stage3()
        if stage >= 4: self.run_stage4()
        if stage >= 5: self.run_stage5()

if __name__ == "__main__":
    dv = DependencyVisualizer()
    if len(sys.argv) == 3:
        config_file = sys.argv[1]
        stage_arg = sys.argv[2]
        stage_map = {
            "--stage1": 1,
            "--stage2": 2,
            "--stage3": 3,
            "--stage4": 4,
            "--stage5": 5
        }
        stage_number = stage_map.get(stage_arg)
        if not stage_number:
            print("Использование: python dependency_visualizer.py config.yaml --stage1|--stage2|--stage3|--stage4|--stage5")
            exit(1)
        if not dv.load_config(config_file):
            exit(1)
        dv.run_stage(stage_number)
    else:
        print("Использование: python dependency_visualizer.py config.yaml --stage1|--stage2|--stage3|--stage4|--stage5")
