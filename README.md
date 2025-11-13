# Dependency Visualizer

## 1. Описание
Инструмент визуализации графа зависимостей пакетов Python.  
Поддерживает тестовый режим и визуализацию с Graphviz.

## 2. Настройки
- package_name
- repository_url
- test_repository_path
- test_mode
- max_depth
- filter_substring

## 3. Запуск
```bash
python dependency_visualizer.py config.yaml --stage1 - Этап 1
python dependency_visualizer.py config.yaml --stage2 - Этап 2
python dependency_visualizer.py config.yaml --stage3 - Этап 3
python dependency_visualizer.py config.yaml --stage4 - Этап 4
python dependency_visualizer.py config.yaml --stage5 - Этап 5
dot -Tpng graph.dot -o graph.png
