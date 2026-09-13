import asyncio
import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from cinecircuit_plugins.subtitle_manager.shared_samples import SharedVideoSamples
from cinecircuit_plugins.subtitle_manager.video_hash import fingerprint, sample_ranges

VIDEO = bytes(range(251)) * 1000


def payload(specs):
    rows = []
    for spec in specs:
        start = SharedVideoSamples._position(len(VIDEO), spec)
        rows.append({'offset': start, 'content_base64': base64.b64encode(VIDEO[start:start+spec['length']]).decode()})
    return {'size': len(VIDEO), 'samples': rows}


def test_concurrent_providers_share_and_keep_original_fingerprints():
    async def run():
        reader = AsyncMock(side_effect=lambda path, specs: payload(specs))
        shared = SharedVideoSamples(SimpleNamespace(read_samples=reader))
        results = await asyncio.gather(*(shared.read_samples('movie.strm', sample_ranges(p)) for p in ['shooter', 'xunlei']))
        for provider, result in zip(['shooter', 'xunlei'], results):
            assert fingerprint(provider, result) == fingerprint(provider, payload(sample_ranges(provider)))
        await shared.read_samples('movie.strm', sample_ranges('shooter'))
        reader.assert_awaited_once()
        assert len(reader.call_args.args[1]) == 4
        await shared.read_samples('other.strm', sample_ranges('xunlei'))
        assert reader.await_count == 2
    asyncio.run(run())


def test_failed_samples_not_cached():
    async def run():
        reader = AsyncMock(side_effect=[ValueError('failed'), payload(sample_ranges('xunlei') + [sample_ranges('shooter')[1]])])
        shared = SharedVideoSamples(SimpleNamespace(read_samples=reader))
        with pytest.raises(ValueError):
            await shared.read_samples('movie.strm', sample_ranges('shooter'))
        result = await shared.read_samples('movie.strm', sample_ranges('xunlei'))
        assert fingerprint('xunlei', result) == fingerprint('xunlei', payload(sample_ranges('xunlei')))
    asyncio.run(run())
