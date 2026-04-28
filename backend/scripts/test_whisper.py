"""
Диагностический скрипт Спринта 1 (CPU-версия).

Проверяет:
  1. Версии PyTorch и NumPy.
  2. Загрузку модели Whisper на CPU.
  3. Транскрибацию аудиофайла.

Запуск:
    python scripts/test_whisper.py путь/к/аудио.mp3
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path


def check_system() -> str:
    """Проверяем окружение. Возвращаем устройство для запуска."""
    import numpy as np
    import torch

    print("=" * 60)
    print("ПРОВЕРКА СИСТЕМЫ")
    print("=" * 60)
    print(f"PyTorch версия: {torch.__version__}")
    print(f"NumPy версия:   {np.__version__}")
    print(f"CPU ядер:       {os.cpu_count()}")

    if torch.cuda.is_available():
        # На GT 710 это сработает, но модель всё равно не запустится.
        # Принудительно остаёмся на CPU.
        print("CUDA вроде доступна, но GT 710 не поддерживается — используем CPU.")
    else:
        print("CUDA недоступна — работаем на CPU.")

    return "cpu"


def load_model(device: str):
    """Загружаем Whisper в режиме int8 для максимальной скорости на CPU."""
    import whisperx

    print()
    print("=" * 60)
    print("ЗАГРУЗКА МОДЕЛИ WHISPER")
    print("=" * 60)

    # На CPU int8 — самый быстрый и экономичный режим.
    compute_type = "int8"
    # На CPU стоит начать с base — small уже заметно медленнее.
    # После успешного теста можно попробовать small.
    model_size = "base"

    print(f"Модель:       {model_size}")
    print(f"Устройство:   {device}")
    print(f"Compute type: {compute_type}")
    print("Грузим... (при первом запуске скачается ~140 МБ для base)")

    t0 = time.perf_counter()
    model = whisperx.load_model(
        model_size,
        device=device,
        compute_type=compute_type,
    )
    print(f"Модель загружена за {time.perf_counter() - t0:.1f} сек.")
    return model


def transcribe(model, audio_path: Path) -> None:
    """Запускаем транскрибацию и печатаем результат."""
    import whisperx

    if not audio_path.exists():
        print(f"\n⚠  Файл не найден: {audio_path}")
        sys.exit(1)

    print()
    print("=" * 60)
    print("ТРАНСКРИБАЦИЯ")
    print("=" * 60)
    print(f"Файл: {audio_path}")

    audio = whisperx.load_audio(str(audio_path))
    duration_sec = len(audio) / 16000
    print(f"Длительность аудио: {duration_sec:.1f} сек.")

    # batch_size на CPU лучше держать маленьким
    t0 = time.perf_counter()
    result = model.transcribe(audio, batch_size=4)
    elapsed = time.perf_counter() - t0

    speed = duration_sec / elapsed if elapsed > 0 else float("inf")
    print(f"Транскрибация заняла {elapsed:.1f} сек.")
    print(f"Скорость: {speed:.2f}x реального времени")
    print(f"Определённый язык: {result.get('language')}")
    print()
    print("--- СЕГМЕНТЫ (первые 10) ---")
    for seg in result["segments"][:10]:
        start = seg["start"]
        end = seg["end"]
        text = seg["text"].strip()
        print(f"[{start:7.2f} → {end:7.2f}]  {text}")

    if len(result["segments"]) > 10:
        print(f"... и ещё {len(result['segments']) - 10} сегментов")


def main() -> None:
    device = check_system()
    model = load_model(device)

    if len(sys.argv) < 2:
        print("\n✓ Модель успешно загружена.")
        print("Чтобы проверить транскрибацию, передайте путь к аудио:")
        print("    python scripts/test_whisper.py путь/к/файлу.mp3")
        return

    audio_path = Path(sys.argv[1])
    transcribe(model, audio_path)
    print("\n✓ Готово. Спринт 1 пройден.")


if __name__ == "__main__":
    main()
