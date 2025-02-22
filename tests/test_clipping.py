from unittest import TestCase

import dask
import numpy as np

from raster_tools import clipping
from raster_tools.raster import Raster, RasterNoDataError
from raster_tools.vector import open_vectors


class TestClipping(TestCase):
    def setUp(self):
        self.dem = Raster("tests/data/elevation.tif")
        self.pods = open_vectors("tests/data/vector/pods.shp")
        self.v10 = self.pods[10]
        self.v10_bounds = dask.compute(self.v10.to_crs(self.dem.crs).bounds)[0]

    def test_core_clip_out_dtype(self):
        result = clipping._clip(self.pods, self.dem)
        self.assertTrue(result.dtype == self.dem.dtype)
        self.assertTrue(result.eval().dtype == self.dem.dtype)

    def test_clip(self):
        res = clipping.clip(self.v10, self.dem)
        truth = Raster("tests/data/clipping_clip_pods_10.tif")
        self.assertTrue(np.allclose(res, truth))

        res = clipping.clip(self.v10, self.dem, bounds=self.v10_bounds)
        self.assertTrue(np.allclose(res, truth))

    def test_erase(self):
        res = clipping.erase(self.v10, self.dem)
        truth = Raster("tests/data/clipping_erase_pods_10.tif")
        self.assertTrue(np.allclose(res, truth))

        res = clipping.erase(self.v10, self.dem, bounds=self.v10_bounds)
        self.assertTrue(np.allclose(res, truth))

    def test_mask(self):
        res = clipping.mask(self.v10, self.dem)
        truth = Raster("tests/data/clipping_mask_pods_10.tif")
        self.assertTrue(np.allclose(res, truth))

        res = clipping.mask(self.v10, self.dem, invert=True)
        truth = Raster("tests/data/clipping_mask_inverted_pods_10.tif")
        self.assertTrue(np.allclose(res, truth))

    def test_envelope(self):
        res = clipping.envelope(self.v10, self.dem)
        truth = Raster("tests/data/clipping_envelope_pods_10.tif")
        self.assertTrue(np.allclose(res, truth))

    def test_errors(self):
        with self.assertRaises(ValueError):
            rs = Raster(np.ones((4, 4)))
            clipping.clip(self.v10, rs)

        with self.assertRaises(ValueError):
            clipping._clip(self.v10, self.dem, bounds=(0, 3))

        with self.assertRaises(ValueError):
            clipping._clip(self.v10, self.dem, invert=True, envelope=True)

        with self.assertRaises(RuntimeError):
            clipping._clip(self.v10, self.dem, bounds=self.v10.bounds)

    def test_clip_box(self):
        self.dem = Raster("tests/data/elevation.tif")
        rs_clipped = Raster("tests/data/elevation_small.tif")
        bounds = [
            rs_clipped.xrs.x.min().item(),
            rs_clipped.xrs.y.min().item(),
            rs_clipped.xrs.x.max().item(),
            rs_clipped.xrs.y.max().item(),
        ]
        test = clipping.clip_box(self.dem, bounds)
        self.assertTrue(test.shape == rs_clipped.shape)
        self.assertTrue(np.allclose(test._values, rs_clipped._values))

        # Test that the mask is also clipped
        x = np.arange(25).reshape((1, 5, 5))
        x[x < 12] = 0
        rs = Raster(x).set_null_value(0).set_crs("epsg:3857")
        self.assertTrue(np.allclose(x == 0, rs._mask))
        rs_clipped = clipping.clip_box(rs, (1, 1, 3, 3))
        mask_truth = np.array([[[1, 1, 1], [1, 0, 0], [0, 0, 0]]], dtype=bool)
        self.assertTrue(np.allclose(rs_clipped._mask, mask_truth))

    def test_clip_out_of_bounds(self):
        with self.assertRaises(RasterNoDataError):
            clipping.clip_box(self.dem, (9e6, 9e6, 10e6, 10e6))
