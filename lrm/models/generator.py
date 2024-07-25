# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.


import torch.nn as nn

from .encoders.dino_wrapper2 import DinoWrapper
from .transformer import TriplaneTransformer
from .rendering.synthesizer_part import TriplaneSynthesizer


class CameraEmbedder(nn.Module):
    """
    Embed camera features to a high-dimensional vector.
    
    Reference:
    DiT: https://github.com/facebookresearch/DiT/blob/main/models.py#L27
    """
    def __init__(self, raw_dim: int, embed_dim: int):
        super().__init__()
        self.mlp = nn.Sequential(
            nn.Linear(raw_dim, embed_dim),
            nn.SiLU(),
            nn.Linear(embed_dim, embed_dim),
        )

    def forward(self, x):
        return self.mlp(x)


class LRMGenerator(nn.Module):
    """
    Full model of the large reconstruction model.
    """
    def __init__(self, camera_embed_dim: int, rendering_samples_per_ray: int,
                 transformer_dim: int, transformer_layers: int, transformer_heads: int,
                 triplane_low_res: int, triplane_high_res: int, triplane_dim: int,
                 encoder_freeze: bool = True, encoder_model_name: str = 'facebook/dinov2-base', encoder_feat_dim: int = 768):
        super().__init__()
        
        # attributes
        self.encoder_feat_dim = encoder_feat_dim
        self.camera_embed_dim = camera_embed_dim

        # modules
        self.encoder = DinoWrapper(
            model_name=encoder_model_name,
            freeze=encoder_freeze,
        )
        self.camera_embedder = CameraEmbedder(
            raw_dim=12+4, embed_dim=camera_embed_dim,
        )
        self.transformer = TriplaneTransformer(
            inner_dim=transformer_dim, num_layers=transformer_layers, num_heads=transformer_heads,
            image_feat_dim=encoder_feat_dim,
            camera_embed_dim=camera_embed_dim,
            triplane_low_res=triplane_low_res, triplane_high_res=triplane_high_res, triplane_dim=triplane_dim,
        )
        self.synthesizer = TriplaneSynthesizer(
            triplane_dim=triplane_dim, samples_per_ray=rendering_samples_per_ray,
        )

    def forward(self, image, camera):
        # image: [N, C_img, H_img, W_img]
        # camera: [N, D_cam_raw]
        assert image.shape[0] == camera.shape[0], "Batch size mismatch for image and camera"
        N = image.shape[0]

        # encode image
        image_feats = self.encoder(image)
        assert image_feats.shape[-1] == self.encoder_feat_dim, \
            f"Feature dimension mismatch: {image_feats.shape[-1]} vs {self.encoder_feat_dim}"

        # embed camera
        camera_embeddings = self.camera_embedder(camera)
        assert camera_embeddings.shape[-1] == self.camera_embed_dim, \
            f"Feature dimension mismatch: {camera_embeddings.shape[-1]} vs {self.camera_embed_dim}"

        # transformer generating planes
        planes = self.transformer(image_feats, camera_embeddings)
        assert planes.shape[0] == N, "Batch size mismatch for planes"
        assert planes.shape[1] == 3, "Planes should have 3 channels"
        return planes

