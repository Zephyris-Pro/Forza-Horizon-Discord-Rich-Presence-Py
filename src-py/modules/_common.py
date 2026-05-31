def fmt_standard_classes(class_id: int) -> str:
    return {0: "D", 1: "C", 2: "B", 3: "A", 4: "S1", 5: "S2", 6: "X"}.get(
        class_id, "Unknown"
    )
