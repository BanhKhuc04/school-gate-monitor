from types import SimpleNamespace
import numpy as np
import pytest

from app.cv.fast_plate_ocr import FastPlateOCRAdapter


def test_adapter_rgb_char_confidence_and_matching_local_config(tmp_path):
    model = tmp_path/'m.onnx'; model.write_bytes(b'model')
    config = tmp_path/'plate.yaml'
    config.write_text('image_color_mode: rgb\nmax_plate_slots: 10\n', encoding='utf-8')
    inputs = []
    def factory(**kwargs):
        assert kwargs['providers'] == ['CPUExecutionProvider']
        def run(image, **options):
            inputs.append(image)
            assert options['return_confidence']
            return [SimpleNamespace(plate='89F123792', char_probs=np.full(9, .91))]
        return SimpleNamespace(run=run)
    adapter = FastPlateOCRAdapter(model, config, factory)
    crop = np.zeros((32, 140, 3), np.uint8); crop[:,:,0] = 200
    result = adapter.read(crop)
    assert inputs[0][0,0].tolist() == [0,0,200]
    assert result['char_confidences'] == [.91]*9
    assert result['confidence'] == .91 and not result['needs_review']
    assert len(result['model_hash']) == 64
    with pytest.raises(ValueError):
        adapter.read(crop.astype(float))


def test_adapter_refuses_config_color_mismatch(tmp_path):
    model = tmp_path/'m.onnx'; model.write_bytes(b'model')
    config = tmp_path/'plate.yaml'; config.write_text('image_color_mode: grayscale')
    with pytest.raises(ValueError, match='RGB'):
        FastPlateOCRAdapter(model, config)
