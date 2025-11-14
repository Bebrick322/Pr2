
#!/usr/bin/env python3
import sys
import os
import re
import yaml
import urllib.request
import urllib.parse
import tarfile
import zipfile
import tempfile
import subprocess
from pathlib import Path
from collections import deque, defaultdict
from typing import Dict, List, Set, Tuple, Optional


class DependencyVisualizer:
    def __init__(self):
        self.config: Dict[str, any] = {
            'package_name': None,
            'repository_url': 'https://pypi.org/simple/',
            'test_repository_path': './test_repo',
            'test_mode': False,
            'max_depth': 3,
            'filter_substring': ''
        }
        self.graph: Dict[str, List[str]] = {}
        self.load_order: List[str] = []
        self.visited_packages: Set[str] = set()
        self.cycles: List[List[str]] = []

    def load_config(self, path: str) -> bool:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                loaded = yaml.safe_load(f) or {}
            self.config.update(loaded)
            return self._validate_config()
        except FileNotFoundError:
            print(f"Error: configuration file '{path}' not found.")
            return False
        except yaml.YAMLError as e:
            print(f"YAML error in '{path}': {e}")
            return False
        except Exception as e:
            print(f"Unknown error loading config: {e}")
            return False

    def _validate_config(self) -> bool:
        errors = []

        pkg = self.config.get('package_name')
        if not pkg or not isinstance(pkg, str) or not pkg.strip():
            errors.append("'package_name' is required and must be a non-empty string.")

        depth = self.config.get('max_depth')
        if not isinstance(depth, int) or depth < 0:
            errors.append("'max_depth' must be a non-negative integer.")

        if not isinstance(self.config.get('test_mode', False), bool):
            errors.append("'test_mode' must be boolean (true/false).")

        url = self.config.get('repository_url')
        if not isinstance(url, str) or not url.strip():
            errors.append("'repository_url' must be a non-empty string.")
        else:
            try:
                parsed = urllib.parse.urlparse(url)
                if not parsed.scheme or not parsed.netloc:
                    errors.append(f"Invalid URL: '{url}'")
            except Exception:
                errors.append(f"Invalid URL: '{url}'")

        test_path = self.config.get('test_repository_path', '')
        if self.config['test_mode']:
            p = Path(test_path)
            if not p.exists():
                errors.append(f"test_repository_path '{test_path}' does not exist.")
            elif not p.is_dir():
                errors.append(f"test_repository_path '{test_path}' is not a directory.")

        if errors:
            print("Configuration errors:")
            for e in errors:
                print(e)
            return False
        return True

    def run_stage1(self):
        print("=" * 60)
        print("STAGE 1: MINIMAL PROTOTYPE WITH CONFIGURATION")
        print("Loaded configuration:")
        for k, v in self.config.items():
            print(f"  {k}: {v!r}")
        print("Configuration validation passed.")

    def get_direct_dependencies(self, package_name: str) -> List[str]:
        if self.config['test_mode']:
            return self._get_direct_dependencies_test(package_name)
        else:
            return self._get_direct_dependencies_pypi(package_name)

    def _get_direct_dependencies_test(self, package_name: str) -> List[str]:
        repo_path = Path(self.config['test_repository_path'])
        deps = []
        for setup_file in repo_path.rglob('setup.py'):
            try:
                content = setup_file.read_text(encoding='utf-8')
                matches = re.findall(r'install_requires\s*=\s*\[(.*?)\]', content, re.DOTALL | re.IGNORECASE)
                for block in matches:
                    pkg_names = re.findall(r'[\'"]?([A-Za-z0-9_][A-Za-z0-9_.-]*)[\'"]?(?:\s*(?:>=|<=|==|!=|>|<).*?)?(?=[,\]\n]|$)', block)
                    deps.extend([name.strip() for name in pkg_names if name.strip()])
            except Exception as e:
                print(f"Warning: error reading {setup_file}: {e}")
        return sorted(set(deps))

    def _get_direct_dependencies_pypi(self, package_name: str) -> List[str]:
        try:
            base_url = self.config['repository_url'].rstrip('/')
            package_url = f"{base_url}/{package_name.lower()}/"
            with urllib.request.urlopen(package_url, timeout=10) as response:
                html = response.read().decode('utf-8')

            pattern = r'href=["\']([^"\']*?{}[^"\']*?\.(?:tar\.gz|zip|whl))["\']'.format(re.escape(package_name.lower()))
            archive_links = re.findall(pattern, html, re.IGNORECASE)
            if not archive_links:
                print(f"Warning: no archives found for '{package_name}'")
                return []

            archive_url = urllib.parse.urljoin(package_url, archive_links[0])

            with tempfile.TemporaryDirectory() as tmp_dir:
                archive_path = Path(tmp_dir) / "package_archive"
                urllib.request.urlretrieve(archive_url, archive_path)

                extracted_dir = Path(tmp_dir) / "extracted"
                extracted_dir.mkdir()
                if archive_path.suffix == '.whl':
                    with zipfile.ZipFile(archive_path, 'r') as zf:
                        zf.extractall(extracted_dir)
                elif archive_path.suffix == '.zip':
                    with zipfile.ZipFile(archive_path, 'r') as zf:
                        zf.extractall(extracted_dir)
                else:
                    with tarfile.open(archive_path, 'r:gz') as tf:
                        tf.extractall(extracted_dir)

                deps = []
                for setup_py in extracted_dir.rglob('setup.py'):
                    try:
                        content = setup_py.read_text(encoding='utf-8', errors='ignore')
                        matches = re.findall(r'install_requires\s*=\s*\[(.*?)\]', content, re.DOTALL | re.IGNORECASE)
                        for block in matches:
                            pkg_names = re.findall(r'[\'"]?([A-Za-z0-9_][A-Za-z0-9_.-]*)[\'"]?(?:\s*(?:>=|<=|==|!=|>|<).*?)?(?=[,\]\n]|$)', block)
                            deps.extend([name.strip() for name in pkg_names if name.strip()])
                    except Exception as e:
                        print(f"Warning: error parsing setup.py: {e}")

                if not deps:
                    for pyproject in extracted_dir.rglob('pyproject.toml'):
                        try:
                            content = pyproject.read_text(encoding='utf-8', errors='ignore')
                            match = re.search(r'\[project\].*?dependencies\s*=\s*\[(.*?)\]', content, re.DOTALL | re.IGNORECASE)
                            if match:
                                block = match.group(1)
                                pkg_names = re.findall(r'[\'"]([^\'"]+)[\'"]', block)
                                clean_names = []
                                for name in pkg_names:
                                    clean = re.split(r'[>=<~!]', name)[0].strip()
                                    if clean:
                                        clean_names.append(clean)
                                deps.extend(clean_names)
                        except Exception as e:
                            print(f"Warning: error parsing pyproject.toml: {e}")

                return sorted(set(deps))

        except urllib.error.HTTPError as e:
            if e.code == 404:
                print(f"Warning: package '{package_name}' not found on PyPI.")
            else:
                print(f"HTTP error for '{package_name}': {e}")
            return []
        except Exception as e:
            print(f"Error getting dependencies for '{package_name}': {e}")
            return []

    def run_stage2(self):
        print("=" * 60)
        print("STAGE 2: DATA COLLECTION (direct dependencies)")
        deps = self.get_direct_dependencies(self.config['package_name'])
        print(f"Direct dependencies of package '{self.config['package_name']}':")
        if deps:
            for i, dep in enumerate(deps, 1):
                print(f"  {i}. {dep}")
        else:
            print("  (no direct dependencies)")
        return deps

    def build_dependency_graph(self) -> Dict[str, List[str]]:
        graph = {}
        visited = set()
        visiting = set()
        self.cycles.clear()

        def bfs_recursive(pkg: str, depth: int):
            if depth > self.config['max_depth']:
                return
            if pkg in visited:
                return
            if pkg in visiting:
                cycle = list(visiting) + [pkg]
                self.cycles.append(cycle)
                print(f"Cycle detected: {' -> '.join(cycle)}")
                return

            deps = self.get_direct_dependencies(pkg)
            filtered_deps = [d for d in deps if self.config['filter_substring'] not in d]
            graph[pkg] = filtered_deps

            visiting.add(pkg)
            for dep in filtered_deps:
                bfs_recursive(dep, depth + 1)
            visiting.remove(pkg)

            visited.add(pkg)

        bfs_recursive(self.config['package_name'], 0)
        self.graph = graph
        return graph

    def run_stage3(self):
        print("=" * 60)
        print("STAGE 3: DEPENDENCY GRAPH CONSTRUCTION")
        print(f"Analyzing package: {self.config['package_name']}")
        print(f"Max depth: {self.config['max_depth']}")
        if self.config['filter_substring']:
            print(f"Filter substring: '{self.config['filter_substring']}'")
        if self.config['test_mode']:
            print("TEST MODE (local repository)")

        self.build_dependency_graph()

        print("\nConstructed graph:")
        if not self.graph:
            print("  (empty graph)")
        for pkg, deps in sorted(self.graph.items()):
            dep_str = ", ".join(deps) if deps else "(none)"
            print(f"  {pkg} -> [{dep_str}]")

        if self.cycles:
            print(f"\nCycles detected: {len(self.cycles)}")
            for i, cycle in enumerate(self.cycles, 1):
                print(f"  Cycle {i}: {' -> '.join(cycle)}")
        else:
            print("\nNo cyclic dependencies detected.")

    def topological_sort(self) -> List[str]:
        in_degree = defaultdict(int)
        all_nodes = set(self.graph.keys())
        for deps in self.graph.values():
            all_nodes.update(deps)

        for node in all_nodes:
            in_degree[node] = 0

        for pkg, deps in self.graph.items():
            for dep in deps:
                in_degree[dep] += 1

        queue = deque([node for node in all_nodes if in_degree[node] == 0])
        order = []

        while queue:
            node = queue.popleft()
            order.append(node)
            for neighbor in self.graph.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        remaining = [node for node in all_nodes if in_degree[node] > 0]
        if remaining:
            print(f"Warning: cyclic nodes excluded from order: {', '.join(remaining)}")

        return order

    def run_stage4(self):
        print("=" * 60)
        print("STAGE 4: LOAD ORDER (topological sorting)")
        self.load_order = self.topological_sort()

        print("Recommended installation order:")
        if self.load_order:
            for i, pkg in enumerate(self.load_order, 1):
                print(f"  {i:2}. {pkg}")
        else:
            print("  (no acyclic nodes)")

        try:
            import subprocess
            result = subprocess.run(
                [sys.executable, "-m", "pipdeptree", "--packages", self.config['package_name'], "-f"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                lines = [line.strip() for line in result.stdout.splitlines() if line.strip() and not line.startswith('Warning')]
                print("\nComparison with pipdeptree (names only):")
                our_order = set(self.load_order)
                pip_order = []
                for line in lines:
                    match = re.match(r'^\s*([A-Za-z0-9_\-]+)', line)
                    if match:
                        name = match.group(1)
                        pip_order.append(name)
                pip_order = [p for p in pip_order if p in our_order]

                print(f"  Our order (acyclic part): {', '.join(self.load_order)}")
                print(f"  pipdeptree (depth order): {', '.join(pip_order)}")

                print("\nExplanation of differences:")
                print("- pipdeptree uses DFS and outputs dependencies in traversal order (by depth),")
                print("  while topological sorting provides a linear order ensuring dependencies")
                print("  are installed BEFORE dependent packages.")
                print("- pipdeptree includes cyclic dependencies (with warning), we exclude them.")
            else:
                print("\npipdeptree not available (not installed or error).")
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            print("\npipdeptree not available (not installed or error).")

    def generate_dot(self) -> str:
        lines = ["digraph dependencies {", '  rankdir=TB;', '  node [shape=box, style=filled, fillcolor="#E0F0FF"];']
        for pkg, deps in self.graph.items():
            for dep in deps:
                color = 'red' if any(pkg in cycle and dep in cycle for cycle in self.cycles) else 'black'
                style = 'bold' if color == 'red' else 'solid'
                lines.append(f'  "{pkg}" -> "{dep}" [color="{color}", style="{style}"];')
        lines.append("}")
        return "\n".join(lines)

    def render_and_show(self, dot_content: str):
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.dot', delete=False) as f_dot:
                f_dot.write(dot_content)
                dot_path = f_dot.name

            png_path = Path(dot_path).with_suffix('.png')

            result = subprocess.run(['dot', '-Tpng', dot_path, '-o', str(png_path)], 
                                  capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"dot failed: {result.stderr}")

            if sys.platform == "darwin":
                subprocess.run(['open', str(png_path)])
            elif sys.platform == "win32":
                os.startfile(str(png_path))
            else:
                subprocess.run(['xdg-open', str(png_path)])

            print(f"Graph saved and opened: {png_path}")
            return png_path

        except FileNotFoundError:
            print("Graphviz (command 'dot') not installed. Install: sudo apt install graphviz")
            return None
        except Exception as e:
            print(f"Error during rendering: {e}")
            return None
        finally:
            try:
                Path(dot_path).unlink(missing_ok=True)
            except:
                pass

    def run_stage5(self):
        print("=" * 60)
        print("STAGE 5: VISUALIZATION")
        dot_content = self.generate_dot()
        print("Generated DOT code:")
        print(dot_content)

        with open("graph.dot", "w", encoding="utf-8") as f:
            f.write(dot_content)
        print("\nDOT file saved as graph.dot.")

        png_path = self.render_and_show(dot_content)
        if png_path:
            print(f"Image opened: {png_path}")

        try:
            result = subprocess.run(
                [sys.executable, "-m", "pipdeptree", "--graph-output", "dot", "--packages", self.config['package_name']],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                print("\nComparison with pipdeptree --graph-output dot:")
                print("- pipdeptree includes ALL dependencies (including nested), we limit by max_depth.")
                print("- pipdeptree does not filter by substring.")
                print("- pipdeptree does not highlight cycles in color (but issues warnings).")
            else:
                print("\npipdeptree --graph-output not available.")
        except:
            print("\npipdeptree --graph-output not available.")

    def run_stage(self, stage: int):
        try:
            if stage >= 1:
                self.run_stage1()
            if stage >= 2:
                self.run_stage2()
            if stage >= 3:
                self.run_stage3()
            if stage >= 4:
                self.run_stage4()
            if stage >= 5:
                self.run_stage5()
        except KeyboardInterrupt:
            print("\nInterrupted by user.")
            sys.exit(1)
        except Exception as e:
            print(f"\nCritical error at stage {stage}: {e}")
            sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python dependency_visualizer.py CONFIG.yaml --stageN")
        print("  where N = 1,2,3,4,5")
        print("\nExamples:")
        print("  python dependency_visualizer.py config.yaml --stage1")
        print("  python dependency_visualizer.py config_test.yaml --stage5")
        sys.exit(1)

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
    if stage_number is None:
        print("Invalid stage. Use: --stage1, --stage2, ..., --stage5")
        sys.exit(1)

    dv = DependencyVisualizer()
    if not dv.load_config(config_file):
        sys.exit(1)

    print(f"\nStarting stage {stage_number}...")
    dv.run_stage(stage_number)
    print("\nStage completed successfully.")
