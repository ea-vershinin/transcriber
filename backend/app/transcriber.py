"""
Обёртка над WhisperX с поддержкой перевода и диаризации.

ASR-модели кэшируются в памяти через LRU на settings.whisper_cache_size слотов.
При превышении лимита вытесняется наименее давно использованная модель.

Align-модели и диаризация кэшируются отдельно (модели там обычно одни и те же).
"""
from __future__ import annotations

import inspect
import logging
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

import whisperx

try:
    from whisperx.diarize import DiarizationPipeline
except ImportError:
    DiarizationPipeline = whisperx.DiarizationPipeline

from app.config import AVAILABLE_MODELS, settings
from app.schemas.transcription import (
    Segment,
    TranscriptionOptions,
    TranscriptionResult,
)

logger = logging.getLogger(__name__)


class DiarizationNotAvailable(RuntimeError):
    pass


class UnknownModelError(ValueError):
    """Пользователь передал имя модели, которого нет в AVAILABLE_MODELS."""


class Transcriber:
    """
    Обёртка над WhisperX. Один экземпляр на всё приложение.

    ASR-модели кэшируются LRU: при обращении модель "поднимается" в начало,
    при переполнении — удаляется наименее свежая.
    """

    def __init__(self) -> None:
        # OrderedDict: ключ — имя модели, значение — загруженная модель.
        # Самый свежий элемент — в конце (move_to_end).
        self._asr_models: "OrderedDict[str, Any]" = OrderedDict()
        self._align_cache: dict[str, tuple[Any, Any]] = {}
        self._diarize_pipeline: Any | None = None

    # ---------- ASR-модели ----------

    def _get_asr_model(self, model_name: str) -> Any:
        """
        Возвращает ASR-модель по имени. Грузит, если её ещё нет.
        Соблюдает LRU-лимит: если моделей больше чем whisper_cache_size,
        вытесняет самую старую.
        """
        if model_name not in AVAILABLE_MODELS:
            raise UnknownModelError(
                f"Неизвестная модель: {model_name}. "
                f"Доступны: {', '.join(AVAILABLE_MODELS)}"
            )

        # Хит кэша: перемещаем в "свежий" конец и возвращаем.
        if model_name in self._asr_models:
            self._asr_models.move_to_end(model_name)
            return self._asr_models[model_name]

        # Промах: нужно загрузить.
        logger.info(
            "Загрузка Whisper: model=%s device=%s compute_type=%s",
            model_name, settings.whisper_device, settings.whisper_compute_type,
        )
        t0 = time.perf_counter()
        model = whisperx.load_model(
            model_name,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
        logger.info("ASR-модель %s загружена за %.1f сек.",
                    model_name, time.perf_counter() - t0)

        self._asr_models[model_name] = model
        # Вытесняем старую, если превысили лимит.
        while len(self._asr_models) > settings.whisper_cache_size:
            evicted_name, _ = self._asr_models.popitem(last=False)
            logger.info("LRU: вытеснена модель %s из кэша", evicted_name)
        return model

    # ---------- Align-модели ----------

    def _get_align_model(self, language: str) -> tuple[Any, Any]:
        if language not in self._align_cache:
            logger.info("Загрузка align-модели для языка %s…", language)
            t0 = time.perf_counter()
            model, metadata = whisperx.load_align_model(
                language_code=language,
                device=settings.whisper_device,
            )
            self._align_cache[language] = (model, metadata)
            logger.info("Align-модель загружена за %.1f сек.",
                        time.perf_counter() - t0)
        return self._align_cache[language]

    # ---------- Диаризация ----------

    def _get_diarize_pipeline(self) -> Any:
        if self._diarize_pipeline is None:
            if not settings.hf_token:
                raise DiarizationNotAvailable(
                    "HF_TOKEN не задан в .env. Получите токен на "
                    "https://huggingface.co/settings/tokens и примите условия "
                    "моделей pyannote/speaker-diarization-community-1 и "
                    "pyannote/segmentation-3.0."
                )
            logger.info("Загрузка pyannote-диаризации…")
            t0 = time.perf_counter()
            sig = inspect.signature(DiarizationPipeline.__init__)
            token_kwarg = "token" if "token" in sig.parameters else "use_auth_token"
            self._diarize_pipeline = DiarizationPipeline(
                **{token_kwarg: settings.hf_token},
                device=settings.whisper_device,
            )
            logger.info("Диаризация-модель загружена за %.1f сек.",
                        time.perf_counter() - t0)
        return self._diarize_pipeline

    # ---------- Главный метод ----------

    def transcribe(
        self,
        audio_path: Path,
        options: TranscriptionOptions | None = None,
    ) -> TranscriptionResult:
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        opts = options or TranscriptionOptions()
        # Решаем какую модель использовать: либо запрошенную, либо дефолтную.
        model_name = opts.model or settings.whisper_model
        asr_model = self._get_asr_model(model_name)

        logger.info("Загрузка аудио: %s", audio_path)
        audio = whisperx.load_audio(str(audio_path))
        duration_sec = len(audio) / 16000
        logger.info(
            "Старт транскрибации: %.1f сек. аудио, model=%s translate=%s "
            "diarize=%s lang=%s",
            duration_sec, model_name, opts.translate, opts.diarize, opts.language,
        )

        t0 = time.perf_counter()
        task = "translate" if opts.translate else "transcribe"
        raw = asr_model.transcribe(
            audio,
            batch_size=settings.whisper_batch_size,
            task=task,
            language=opts.language,
        )
        detected_language = raw.get("language", opts.language or "unknown")
        output_language = "en" if opts.translate else detected_language

        if opts.diarize:
            if opts.translate:
                logger.warning(
                    "diarize + translate нельзя одновременно. Диаризация отключена."
                )
            else:
                raw = self._align_and_diarize(raw, audio, detected_language)

        processing_sec = time.perf_counter() - t0
        speed = duration_sec / processing_sec if processing_sec > 0 else float("inf")
        logger.info("Готово за %.1f сек. (скорость %.2fx RT)", processing_sec, speed)

        segments = [
            Segment(
                start=float(seg["start"]),
                end=float(seg["end"]),
                text=seg["text"].strip(),
                speaker=seg.get("speaker"),
            )
            for seg in raw["segments"]
        ]

        return TranscriptionResult(
            language=output_language,
            duration_sec=duration_sec,
            processing_sec=processing_sec,
            segments=segments,
            translated=opts.translate,
            model_used=model_name,
        )

    # ---------- Вспомогательное ----------

    def _align_and_diarize(
        self,
        raw: dict,
        audio: Any,
        language: str,
    ) -> dict:
        logger.info("Выравнивание слов (язык: %s)…", language)
        align_model, metadata = self._get_align_model(language)
        raw = whisperx.align(
            raw["segments"],
            align_model,
            metadata,
            audio,
            device=settings.whisper_device,
            return_char_alignments=False,
        )

        logger.info("Диаризация (pyannote)…")
        diarize_pipeline = self._get_diarize_pipeline()
        diarize_segments = diarize_pipeline(audio)

        logger.info("Сшивка сегментов со спикерами…")
        raw = whisperx.assign_word_speakers(diarize_segments, raw)

        normalized_segments = []
        for seg in raw["segments"]:
            normalized_segments.append({
                "start": seg["start"],
                "end": seg["end"],
                "text": seg["text"],
                "speaker": seg.get("speaker"),
            })
        return {"segments": normalized_segments}


transcriber = Transcriber()
