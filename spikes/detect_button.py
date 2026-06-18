"""Детектор кнопки руля: пишет индексы нажатых кнопок в spikes/ocr/buttons.txt."""
import os
import time
import pygame

OUT = os.path.join(os.path.dirname(__file__), "ocr", "buttons.txt")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

pygame.init()
pygame.joystick.init()
j = pygame.joystick.Joystick(0)
j.init()

seen = {}
t0 = time.time()
with open(OUT, "w", encoding="utf-8") as f:
    f.write(f"руль: {j.get_name()}, кнопок: {j.get_numbuttons()}\nслушаю 30 секунд…\n")
    f.flush()
    while time.time() - t0 < 30:
        pygame.event.pump()
        for b in range(j.get_numbuttons()):
            if j.get_button(b):
                if b not in seen:
                    f.write(f"кнопка индекс {b}\n"); f.flush()
                seen[b] = seen.get(b, 0) + 1
        time.sleep(0.02)
    f.write("итог: " + (", ".join(str(b) for b in sorted(seen)) if seen else "ничего") + "\n")
pygame.quit()
