import sys
import time

from app.services.android_sms_service import AndroidSMSService

MESSAGE = (
    "Dear Tenants, sink tap water is temporarily unavailable. "
    "Bathroom tap water remains available for general use. "
    "For drinking and cooking, kindly boil the water first. "
    "We appreciate your understanding and will update you once sink water is restored."
)
DELAY_SECONDS = 4


def normalize(raw):
    n = "".join(ch for ch in raw if ch.isdigit())
    if n.startswith("0"):
        n = "254" + n[1:]
    elif len(n) == 9:
        n = "254" + n
    return n if len(n) == 12 and n.startswith("254") else None


def main():
    path = sys.argv[1]
    with open(path) as f:
        lines = f.read().replace(",", "\n").splitlines()

    numbers, bad = [], []
    for line in lines:
        if not line.strip():
            continue
        n = normalize(line)
        if n is None:
            bad.append(line.strip())
        elif n not in numbers:
            numbers.append(n)

    print(f"{len(numbers)} valid numbers, {len(bad)} rejected")
    for b in bad:
        print(f"  rejected: {b}")
    print(f"\nMessage ({len(MESSAGE)} chars):\n{MESSAGE}\n")

    if not numbers or input("Type YES to send: ") != "YES":
        print("Cancelled.")
        return

    sms = AndroidSMSService()
    failed = []
    for i, n in enumerate(numbers, 1):
        try:
            result = sms.send_message(n, MESSAGE)
        except Exception as e:
            print(f"  error: {e}")
            result = None
        print(f"[{i}/{len(numbers)}] {n}: {'sent' if result is not None else 'FAILED'}")
        if result is None:
            failed.append(n)
        time.sleep(DELAY_SECONDS)

    if failed:
        with open(path + ".failed", "w") as f:
            f.write("\n".join(failed))
        print(f"\n{len(failed)} failed. Saved to {path}.failed, rerun with that file.")
    else:
        print("\nAll sent.")


if __name__ == "__main__":
    main()