import sys
p = sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/sample_setup.sto"
raw = open(p, "rb").read()
printable = sum(32 <= b < 127 or b in (9, 10, 13) for b in raw)
print(f"размер={len(raw)} печатных_байт={printable} ({printable/len(raw):.0%})")
print("--- первые 512 байт как текст ---")
print(raw[:512].decode("latin-1"))
print("--- hex первых 64 байт ---")
print(raw[:64].hex(" "))
