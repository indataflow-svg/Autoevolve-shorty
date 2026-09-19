from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

from . import __version__
from .ingest import load_campaign, package_sha256
from .assets import build_asset_plan, validate_reference_registry
from .models import AssetRecord
from .memory import AssetMemory
from .omniroute_image import OmniRouteImageProvider
from .pexels import PexelsProvider
from .pixabay import PixabayProvider
from .coverr import CoverrProvider
from .renderer import render_carousel
from .resolver import AssetResolver
from .video import video_manifest
from .storyboard import compile_storyboard
from .mixed_video import load_asset_records, render_video
from .platform_script import load_platform_script
from .catalog import LocalCatalogProvider, index_approved_media
from .pool import OwnedPoolProvider, clip_to_candidate, ingest_pool, load_pool, match_for_scene, tag_clips
from .lordicon import LordiconProvider
from .media_acquisition import acquire_selected_media
from .media_intelligence import FederatedMediaSearch, build_media_search_plan, write_search_result
from .wikimedia import WikimediaProvider
from .voice_bakeoff import DEFAULT_MARKETING_VOICES, installed_edge_voices, render_voice_bakeoff
from .scene_images import search_scene_images, write_scene_search_result


def _dump(value):
    print(json.dumps(value, indent=2))


def _records(path: str | None) -> list[AssetRecord]:
    if not path:
        return []
    return [AssetRecord.model_validate(item) for item in json.loads(Path(path).read_text(encoding="utf-8"))]


def main() -> int:
    parser = argparse.ArgumentParser(prog="company-core-g2")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    pexels = sub.add_parser("pexels-search")
    pexels.add_argument("query")
    pexels.add_argument("--limit", type=int, default=5)
    pexels.add_argument("--media-type", choices=["image", "video"], default="image")
    pixabay = sub.add_parser("pixabay-search")
    pixabay.add_argument("query")
    pixabay.add_argument("--limit", type=int, default=5)
    pixabay.add_argument("--media-type", choices=["image", "video"], default="image")
    references = sub.add_parser("check-references")
    references.add_argument("--root", default="assets/references")
    references.add_argument("--registry", default="assets/references/reference_registry.json")
    plan = sub.add_parser("plan-assets")
    plan.add_argument("campaign")
    plan.add_argument("--output")
    resolve = sub.add_parser("resolve-assets")
    resolve.add_argument("campaign")
    resolve.add_argument("--output", required=True)
    resolve.add_argument("--reference-root", default="assets/references")
    resolve.add_argument("--reference-registry", default="assets/references/reference_registry.json")
    resolve.add_argument("--limit", type=int, default=5)
    resolve.add_argument("--memory", default="data/asset_memory.json")
    remember = sub.add_parser("remember-asset")
    remember.add_argument("manifest")
    remember.add_argument("--slide", required=True, type=int)
    remember.add_argument("--memory", default="data/asset_memory.json")
    validate = sub.add_parser("validate")
    validate.add_argument("campaign")
    video = sub.add_parser("video-manifest")
    video.add_argument("campaign")
    video.add_argument("--output", required=True)
    video.add_argument("--duration", type=int, default=45)
    render = sub.add_parser("render-carousel")
    render.add_argument("campaign")
    render.add_argument("--output", required=True)
    render.add_argument("--logo", required=True)
    render.add_argument("--asset-root")
    render.add_argument("--asset-manifest")
    render.add_argument("--proof-placeholders", action="store_true")
    mixed_plan = sub.add_parser("mixed-video-plan")
    mixed_plan.add_argument("campaign")
    mixed_plan.add_argument("--output", required=True)
    mixed_plan.add_argument("--duration", type=int)
    mixed_plan.add_argument("--platform", choices=["youtube", "shorts", "tiktok"], default="shorts")
    mixed_plan.add_argument("--platform-script")
    media_plan = sub.add_parser("media-search-plan")
    media_plan.add_argument("campaign")
    media_plan.add_argument("--output", required=True)
    media_plan.add_argument("--duration", type=int)
    media_plan.add_argument("--platform", choices=["youtube", "shorts", "tiktok"], default="shorts")
    media_plan.add_argument("--platform-script")
    media_search = sub.add_parser("search-media")
    media_search.add_argument("campaign")
    media_search.add_argument("--output", required=True)
    media_search.add_argument("--duration", type=int)
    media_search.add_argument("--platform", choices=["youtube", "shorts", "tiktok"], default="shorts")
    media_search.add_argument("--platform-script")
    media_search.add_argument("--deadline", type=float, default=15.0)
    media_search.add_argument("--limit", type=int, default=6)
    media_search.add_argument("--catalog", default="data/media_catalog.json")
    media_search.add_argument("--pool", default="assets/owned/pool.json")
    media_search.add_argument("--no-pool", action="store_true")
    media_search.add_argument("--images-only", action="store_true")
    pool_ingest = sub.add_parser("pool-ingest")
    pool_ingest.add_argument("--pool-root", default="assets/owned")
    pool_ingest.add_argument("--pool", default="assets/owned/pool.json")
    pool_tag = sub.add_parser("pool-tag")
    pool_tag.add_argument("--pool", default="assets/owned/pool.json")
    pool_tag.add_argument("--campaign")
    pool_tag.add_argument("--force", action="store_true")
    pool_tag.add_argument("--limit", type=int, default=25)
    pool_search = sub.add_parser("pool-search")
    pool_search.add_argument("query")
    pool_search.add_argument("--pool", default="assets/owned/pool.json")
    pool_search.add_argument("--limit", type=int, default=5)
    pool_match = sub.add_parser("pool-match")
    pool_match.add_argument("campaign")
    pool_match.add_argument("--pool", default="assets/owned/pool.json")
    pool_match.add_argument("--scene", type=int, default=0)
    pool_match.add_argument("--duration", type=int)
    pool_match.add_argument("--platform", choices=["youtube", "shorts", "tiktok"], default="shorts")
    pool_match.add_argument("--platform-script")
    pool_match.add_argument("--limit", type=int, default=3)
    acquire = sub.add_parser("acquire-media")
    acquire.add_argument("search_result")
    acquire.add_argument("--output", required=True)
    acquire.add_argument("--timeout", type=int, default=45)
    acquire.add_argument("--workers", type=int, default=1)
    scene_images = sub.add_parser("search-scene-images")
    scene_images.add_argument("plan")
    scene_images.add_argument("--output", required=True)
    scene_images.add_argument("--deadline", type=float, default=8.0)
    scene_images.add_argument("--limit", type=int, default=4)
    index_media = sub.add_parser("index-approved-media")
    index_media.add_argument("campaign")
    index_media.add_argument("--asset-manifest", required=True)
    index_media.add_argument("--asset-root", required=True)
    index_media.add_argument("--catalog", default="data/media_catalog.json")
    mixed_render = sub.add_parser("render-mixed-video")
    mixed_render.add_argument("campaign")
    mixed_render.add_argument("--asset-manifest", required=True)
    mixed_render.add_argument("--asset-root", required=True)
    mixed_render.add_argument("--showcase", required=True)
    mixed_render.add_argument("--outro", required=True)
    mixed_render.add_argument("--output", required=True)
    mixed_render.add_argument("--duration", type=int)
    mixed_render.add_argument("--platform", choices=["youtube", "shorts", "tiktok"], default="shorts")
    mixed_render.add_argument("--platform-script")
    mixed_render.add_argument("--review", action="store_true")
    mixed_render.add_argument("--voice-mode", choices=["silent", "edge", "system", "kokoro"], default="silent")
    mixed_render.add_argument("--voice", default="en-GB-RyanNeural")
    mixed_render.add_argument("--subtitle-engine", choices=["auto", "provider-timed", "faster-whisper", "timed-proof", "none"], default="auto")
    mixed_render.add_argument("--whisper-model", default="base.en")
    mixed_render.add_argument("--speed", type=float, default=1.0)
    mixed_render.add_argument("--duration-scale", type=float, default=1.0)
    bakeoff = sub.add_parser("voice-bakeoff")
    bakeoff.add_argument("campaign")
    bakeoff.add_argument("--output", required=True)
    bakeoff.add_argument("--duration", type=int)
    bakeoff.add_argument("--platform", choices=["youtube", "shorts", "tiktok"], default="shorts")
    bakeoff.add_argument("--platform-script")
    bakeoff.add_argument("--voices", nargs="+")
    bakeoff.add_argument("--all-english", action="store_true")
    bakeoff.add_argument("--speed", type=float, default=1.0)
    bakeoff.add_argument("--scene-timeout", type=float, default=45.0)
    bakeoff.add_argument("--attempts", type=int, default=2)
    bakeoff.add_argument("--retry-base-seconds", type=float, default=1.0)
    args = parser.parse_args()

    if args.command == "doctor":
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        image_provider = OmniRouteImageProvider()
        try:
            pool = load_pool("assets/owned/pool.json")
            pool_clips = pool["clips"]
            pool_check = {
                "configured": True,
                "clips": len(pool_clips),
                "tagged": sum(1 for item in pool_clips if item.get("topics")),
                "consented": sum(1 for item in pool_clips if item.get("consent")),
                "required_for": "owned product-demo and face footage preferred over stock",
            }
        except Exception as exc:
            pool_check = {"configured": False, "error": f"{type(exc).__name__}: {exc}",
                          "required_for": "run pool-ingest after dropping footage in assets/owned"}
        try:
            import kokoro  # noqa: F401
            kokoro_available = True
        except ImportError:
            kokoro_available = False
        try:
            import faster_whisper  # noqa: F401
            faster_whisper_available = True
        except ImportError:
            faster_whisper_available = False
        result = {"ok": bool(ffmpeg and ffprobe), "checks": {
            "ffmpeg": {"ok": bool(ffmpeg), "path": ffmpeg},
            "ffprobe": {"ok": bool(ffprobe), "path": ffprobe},
            "renderer": {"ok": True, "canvas": "1080x1350"},
            "mixed_video_renderer": {"ok": True, "canvas": "1080x1920", "fps": 30},
            "edge_voice": {
                "configured": bool(shutil.which("edge-tts")),
                "required_for": "preferred clean neural voice and native subtitle boundaries",
            },
            "kokoro": {"configured": kokoro_available, "required_for": "production voice only"},
            "system_voice": {"configured": bool(shutil.which("espeak-ng") or shutil.which("espeak")), "required_for": "zero-model fallback"},
            "faster_whisper": {"configured": faster_whisper_available, "required_for": "uploaded or externally recorded speech only"},
            "pexels": {"configured": bool(os.getenv("PEXELS_API_KEY"))},
            "pixabay": {"configured": bool(os.getenv("PIXABAY_API_KEY"))},
            "coverr": {"configured": bool(os.getenv("COVERR_API_KEY")), "required_for": "optional expanded stock-video discovery"},
            "wikimedia": {"configured": True, "required_for": "open-license image and video discovery"},
            "lordicon": {"configured": bool(os.getenv("LORDICON_API_TOKEN")), "required_for": "optional free vector animation discovery"},
            "media_intelligence": {"configured": True, "policy": "deadline-bound federated retrieval"},
            "owned_pool": pool_check,
            "omniroute_image": {"configured": image_provider.configured, "model": image_provider.model or None},
        }}
        _dump(result)
        return 0 if result["ok"] else 1
    if args.command == "pexels-search":
        _dump({"provider": "pexels", "results": [item.model_dump(mode="json") for item in PexelsProvider().search(args.query, args.limit, args.media_type)]})
        return 0
    if args.command == "pixabay-search":
        _dump({"provider": "pixabay", "results": [item.model_dump(mode="json") for item in PixabayProvider().search(args.query, args.limit, args.media_type)]})
        return 0
    if args.command == "check-references":
        _dump(validate_reference_registry(args.root, args.registry))
        return 0
    if args.command == "remember-asset":
        records = _records(args.manifest)
        record = next((item for item in records if item.slide_number == args.slide), None)
        if not record:
            raise SystemExit(f"slide {args.slide} not present in manifest")
        if not record.approved or not record.sha256 or not record.perceptual_hash:
            raise SystemExit("only founder-approved fingerprinted assets can enter media memory")
        AssetMemory(args.memory).add({
            "slide_number": record.slide_number,
            "candidate_id": record.candidate_id,
            "sha256": record.sha256,
            "perceptual_hash": record.perceptual_hash,
            "provider": record.provider,
        })
        _dump({"ok": True, "remembered_slide": record.slide_number, "memory": args.memory})
        return 0
    if args.command == "acquire-media":
        value = json.loads(Path(args.search_result).read_text(encoding="utf-8"))
        _dump(acquire_selected_media(value, args.output, args.timeout, args.workers))
        return 0
    if args.command == "search-scene-images":
        value = search_scene_images(
            args.plan,
            deadline=max(1.0, args.deadline),
            limit=max(1, min(args.limit, 10)),
        )
        write_scene_search_result(value, args.output)
        _dump(value)
        return 0
    if args.command == "pool-ingest":
        _dump(ingest_pool(args.pool_root, args.pool))
        return 0
    if args.command == "pool-tag":
        claim_ids = None
        if args.campaign:
            claim_ids = load_campaign(args.campaign).claim_ids
        _dump(tag_clips(args.pool, claim_ids=claim_ids, force=args.force,
                        limit=max(1, min(args.limit, 100))))
        return 0
    if args.command == "pool-search":
        provider = OwnedPoolProvider(args.pool)
        _dump({"provider": "owned", "pool": str(args.pool), "results": [
            item.model_dump(mode="json")
            for item in provider.search(args.query, max(1, min(args.limit, 20)), "video")
        ]})
        return 0
    if args.command == "pool-match":
        campaign = load_campaign(args.campaign)
        script = load_platform_script(args.platform_script, campaign.campaign_id, args.platform) if args.platform_script else None
        storyboard = compile_storyboard(campaign, args.duration, args.platform, script)
        search_plan = build_media_search_plan(campaign, storyboard)
        slides = {slide.number: slide for slide in campaign.slides}
        provider = OwnedPoolProvider(args.pool)
        clips = provider.clips()
        by_id = {clip.clip_id: clip for clip in clips}
        scenes = []
        for requirement in search_plan.requirements:
            if args.scene and requirement.scene_number != args.scene:
                continue
            slide = slides[requirement.scene_number]
            width, height = (int(value) for value in search_plan.resolution.split("x"))
            matches = match_for_scene(
                clips, purpose=requirement.purpose, queries=requirement.queries,
                narration=requirement.visual_concept, goal=campaign.objective,
                claim_ids=slide.claim_ids, duration_seconds=requirement.duration_seconds,
                orientation="portrait" if height >= width else "landscape",
                minimum_width=width, minimum_height=height,
                limit=max(1, min(args.limit, 10)),
            )
            for match in matches:
                found = by_id.get(match["clip_id"])
                match["candidate"] = (
                    clip_to_candidate(found, provider.pool_root).model_dump(mode="json")
                    if found and match["score"] > 0 else None
                )
            scenes.append({"scene": requirement.scene_number, "purpose": requirement.purpose,
                           "claim_ids": slide.claim_ids, "matches": matches})
        _dump({"campaign_id": campaign.campaign_id, "goal": campaign.objective,
               "pool": str(args.pool), "scenes": scenes})
        return 0
    campaign = load_campaign(args.campaign)
    if args.command == "voice-bakeoff":
        if args.all_english and args.voices:
            raise SystemExit("choose either --all-english or --voices, not both")
        script = load_platform_script(args.platform_script, campaign.campaign_id, args.platform) if args.platform_script else None
        plan = compile_storyboard(campaign, args.duration, args.platform, script)
        voices = installed_edge_voices("en-") if args.all_english else (args.voices or DEFAULT_MARKETING_VOICES)
        _dump(render_voice_bakeoff(
            plan, args.output, voices, args.speed,
            scene_timeout_seconds=args.scene_timeout,
            attempts=max(1, args.attempts),
            retry_base_seconds=max(0.0, args.retry_base_seconds),
        ))
        return 0
    if args.command == "index-approved-media":
        _dump(index_approved_media(
            load_asset_records(args.asset_manifest), campaign, args.asset_root, args.catalog,
        ))
        return 0
    if args.command == "plan-assets":
        value = build_asset_plan(campaign).model_dump(mode="json")
        if args.output:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        _dump(value)
        return 0
    if args.command == "mixed-video-plan":
        script = load_platform_script(args.platform_script, campaign.campaign_id, args.platform) if args.platform_script else None
        value = compile_storyboard(campaign, args.duration, args.platform, script).model_dump(mode="json")
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        _dump(value)
        return 0
    if args.command in {"media-search-plan", "search-media"}:
        script = load_platform_script(args.platform_script, campaign.campaign_id, args.platform) if args.platform_script else None
        storyboard = compile_storyboard(campaign, args.duration, args.platform, script)
        search_plan = build_media_search_plan(campaign, storyboard)
        if getattr(args, "images_only", False):
            requirements = [
                requirement.model_copy(update={
                    "preferred_media_type": "image",
                    "allowed_media_types": ["image"],
                    "queries": requirement.queries[:2],
                })
                for requirement in search_plan.requirements
                if requirement.purpose not in {"control_system", "outcome_cta"}
            ]
            search_plan = search_plan.model_copy(update={"requirements": requirements})
        if args.command == "media-search-plan":
            value = search_plan.model_dump(mode="json")
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        else:
            search_plan = search_plan.model_copy(update={
                "search_deadline_seconds": max(1.0, args.deadline),
                "candidates_per_provider": max(1, min(args.limit, 20)),
            })
            providers = [
                LocalCatalogProvider(args.catalog),
                PexelsProvider(timeout=max(2, min(int(args.deadline), 10))),
                PixabayProvider(timeout=max(2, min(int(args.deadline), 10))),
                CoverrProvider(timeout=max(2, min(int(args.deadline), 10))),
            ]
            if not getattr(args, "no_pool", False) and not getattr(args, "images_only", False):
                providers.insert(0, OwnedPoolProvider(args.pool))
            if not getattr(args, "images_only", False):
                providers.extend([
                    WikimediaProvider(timeout=max(2, min(int(args.deadline), 10))),
                    LordiconProvider(timeout=max(2, min(int(args.deadline), 10))),
                ])
            value = FederatedMediaSearch(
                providers,
                max_workers=6 if getattr(args, "images_only", False) else 8,
            ).search(search_plan)
            write_search_result(value, args.output)
        _dump(value)
        return 0
    if args.command == "render-mixed-video":
        script = load_platform_script(args.platform_script, campaign.campaign_id, args.platform) if args.platform_script else None
        plan = compile_storyboard(campaign, args.duration, args.platform, script)
        value = render_video(
            campaign, plan, load_asset_records(args.asset_manifest), args.asset_root,
            args.showcase, args.outro,
            args.output, review=args.review, voice_mode=args.voice_mode, voice=args.voice,
            subtitle_engine=args.subtitle_engine,
            whisper_model=args.whisper_model, speed=args.speed, duration_scale=args.duration_scale,
        )
        _dump(value)
        return 0
    if args.command == "resolve-assets":
        _dump(AssetResolver().resolve(campaign, args.output, args.reference_root, args.reference_registry, args.limit, args.memory))
        return 0
    if args.command == "validate":
        _dump({"ok": True, "campaign_id": campaign.campaign_id, "source_package_sha256": package_sha256(campaign)})
        return 0
    if args.command == "video-manifest":
        value = video_manifest(campaign, args.duration).model_dump(mode="json")
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        _dump(value)
        return 0
    result = render_carousel(campaign, args.output, args.logo, args.asset_root, _records(args.asset_manifest), args.proof_placeholders)
    _dump(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
