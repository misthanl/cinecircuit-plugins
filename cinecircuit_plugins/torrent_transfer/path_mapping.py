from .._shared.seeding import map_path


def mapped_save_path(path, config):
    mappings = str(config.get("path_mappings") or "").strip()
    if not mappings:
        return map_path(path, config.get("frompath"), config.get("topath"))
    sources, targets = [], []
    for index, line in enumerate(mappings.splitlines(), 1):
        if not line.strip():
            continue
        if line.count("#") != 1:
            raise ValueError(f"保存目录映射第 {index} 行应为：源目录#目标目录")
        source, target = (part.strip() for part in line.split("#", 1))
        if not source or not target:
            raise ValueError(f"保存目录映射第 {index} 行的源目录和目标目录不能为空")
        sources.append(source)
        targets.append(target)
    return map_path(path, "\n".join(sources), "\n".join(targets))
