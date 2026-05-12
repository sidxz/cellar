"""Temporal task queue constants.

Single queue for now. Split CPU-bound vs IO-bound later when
curve fitting / Markush activities arrive.
"""

MAIN_TASK_QUEUE = "cellar-main"

# Number of CDD/bulk molecules per processing chunk
CHUNK_SIZE = 250

# Plates carry ~96 wells each, so smaller chunks to stay under Temporal's 4MB payload limit
PLATE_CHUNK_SIZE = 5
