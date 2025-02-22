import unittest

import affine
import dask
import numpy as np
import rasterio as rio
import xarray as xr

import raster_tools.focal as focal
from raster_tools import Raster, band_concat
from raster_tools.dtypes import DTYPE_INPUT_TO_DTYPE
from raster_tools.raster import _BINARY_ARITHMETIC_OPS, _BINARY_LOGICAL_OPS

TEST_ARRAY = np.array(
    [
        [1, 3, 4, 4, 3, 2],
        [7, 3, 2, 6, 4, 6],
        [5, 8, 7, 5, 6, 6],
        [1, 4, 5, -1, 5, 1],
        [4, 7, 5, -1, 2, 6],
        [1, 2, 2, 1, 3, 4],
    ]
)


def rs_eq_array(rs, ar):
    return (rs.xrs.values == ar).all()


class TestRasterCreation(unittest.TestCase):
    def test_ctor_errors(self):
        with self.assertRaises(ValueError):
            Raster(np.ones(4))
        with self.assertRaises(ValueError):
            Raster(np.ones((1, 3, 4, 4)))

    def test_increasing_coords(self):
        # This raster has an inverted y axis
        rs = Raster("tests/data/elevation_small.tif")
        x, y = rs.xrs.x.values, rs.xrs.y.values
        self.assertTrue((np.diff(x) > 0).all())
        self.assertTrue((np.diff(y) > 0).all())

        rs = Raster(TEST_ARRAY)
        x, y = rs.xrs.x.values, rs.xrs.y.values
        self.assertTrue((np.diff(x) > 0).all())
        self.assertTrue((np.diff(y) > 0).all())

    def test_creation_from_numpy(self):
        for nprs in [np.ones((6, 6)), np.ones((1, 6, 6)), np.ones((4, 5, 5))]:
            rs = Raster(nprs)
            shape = nprs.shape if len(nprs.shape) == 3 else (1, *nprs.shape)
            self.assertEqual(rs.shape, shape)
            self.assertTrue(rs_eq_array(rs, nprs))

        rs = Raster(TEST_ARRAY)
        # Band dim has been added
        self.assertTrue(rs.shape == (1, 6, 6))
        # Band dim starts at 1
        self.assertTrue((rs.xrs.band == [1]).all())
        # x/y dims start at 0 and increase
        self.assertTrue((rs.xrs.x == np.arange(0, 6)).all())
        self.assertTrue((rs.xrs.y == np.arange(0, 6)).all())
        # No null value determined for int type
        self.assertIsNone(rs.null_value)

        rs = Raster(TEST_ARRAY.astype(float))
        self.assertTrue(np.isnan(rs.null_value))


class TestProperties(unittest.TestCase):
    def test__attrs(self):
        rs = Raster("tests/data/elevation_small.tif")
        self.assertDictEqual(rs._attrs, rs.xrs.attrs)
        rs._attrs = {}
        self.assertDictEqual(rs._attrs, {})

    def test__masked(self):
        rs = Raster("tests/data/elevation_small.tif")
        self.assertTrue(rs._masked)
        rs = Raster("tests/data/null_values.tiff")
        self.assertTrue(rs._masked)
        x = np.ones((1, 3, 3))
        rs = Raster(x)
        self.assertTrue(rs._masked)
        rs = Raster(x.astype(int))
        self.assertFalse(rs._masked)

    def test__values(self):
        rs = Raster("tests/data/elevation_small.tif")
        self.assertTrue((rs._values == rs.xrs.values).all())

    def test__null_value(self):
        rs = Raster("tests/data/elevation_small.tif")
        self.assertEqual(rs._null_value, rs.xrs.attrs["_FillValue"])
        rs._null_value = 1
        self.assertEqual(rs._null_value, 1)
        self.assertEqual(rs.xrs.attrs["_FillValue"], 1)

    def test_null_value(self):
        rs = Raster("tests/data/elevation_small.tif")
        self.assertEqual(rs.null_value, rs.xrs.attrs["_FillValue"])

    def test_dtype(self):
        rs = Raster("tests/data/elevation_small.tif")
        self.assertTrue(rs.dtype == rs.xrs.dtype)

    def test_shape(self):
        rs = Raster("tests/data/elevation_small.tif")
        self.assertTrue(rs.shape == rs.xrs.shape)
        self.assertIsInstance(rs.shape, tuple)

    def test_crs(self):
        rs = Raster("tests/data/elevation_small.tif")
        self.assertIsInstance(rs.crs, rio.crs.CRS)
        self.assertTrue(rs.crs == rs.xrs.rio.crs)

        x = np.arange(25).reshape((5, 5))
        rs = Raster(x)
        self.assertIsNone(rs.crs)

    def test_affine(self):
        rs = Raster("tests/data/elevation_small.tif")
        self.assertIsInstance(rs.affine, affine.Affine)
        self.assertTrue(rs.affine == rs.xrs.rio.transform())

    def test_resolution(self):
        rs = Raster("tests/data/elevation_small.tif")
        self.assertTupleEqual(rs.resolution, rs.xrs.rio.resolution(True))

        r = np.arange(25).reshape((5, 5))
        rs = Raster(r)
        self.assertTupleEqual(rs.resolution, rs.xrs.rio.resolution(True))


def test_property_xrs():
    rs = Raster("tests/data/elevation_small.tif")
    assert hasattr(rs, "xrs")
    assert isinstance(rs.xrs, xr.DataArray)
    assert rs.xrs is rs._rs


def test_property__data():
    rs = Raster("tests/data/elevation_small.tif")
    assert hasattr(rs, "_data")
    assert isinstance(rs._data, dask.array.Array)
    assert rs._data is rs._rs.data


class TestRasterMath(unittest.TestCase):
    def setUp(self):
        self.rs1 = Raster("tests/data/elevation_small.tif")
        self.rs1_np = self.rs1.xrs.values
        self.rs2 = Raster("tests/data/elevation2_small.tif")
        self.rs2_np = self.rs2.xrs.values

    def tearDown(self):
        self.rs1.close()
        self.rs2.close()

    def test_add(self):
        # Raster + raster
        truth = self.rs1_np + self.rs2_np
        rst = self.rs1.add(self.rs2)
        self.assertTrue(rs_eq_array(rst, truth))
        rst = self.rs2.add(self.rs1)
        self.assertTrue(rs_eq_array(rst, truth))
        rst = self.rs1 + self.rs2
        self.assertTrue(rs_eq_array(rst, truth))
        rst = self.rs2 + self.rs1
        self.assertTrue(rs_eq_array(rst, truth))
        # Raster + scalar
        for v in [-23, 0, 1, 2, 321]:
            truth = self.rs1_np + v
            rst = self.rs1.add(v)
            self.assertTrue(rs_eq_array(rst, truth))
            rst = self.rs1 + v
            self.assertTrue(rs_eq_array(rst, truth))
            rst = v + self.rs1
            self.assertTrue(rs_eq_array(rst, truth))
        for v in [-23.3, 0.0, 1.0, 2.0, 321.4]:
            truth = self.rs1_np + v
            rst = self.rs1.add(v)
            self.assertTrue(rs_eq_array(rst, truth))
            rst = self.rs1 + v
            self.assertTrue(rs_eq_array(rst, truth))
            rst = v + self.rs1
            self.assertTrue(rs_eq_array(rst, truth))

    def test_subtract(self):
        # Raster - raster
        truth = self.rs1_np - self.rs2_np
        rst = self.rs1.subtract(self.rs2)
        self.assertTrue(rs_eq_array(rst, truth))
        rst = self.rs2.subtract(self.rs1)
        self.assertTrue(rs_eq_array(rst, -truth))
        rst = self.rs1 - self.rs2
        self.assertTrue(rs_eq_array(rst, truth))
        rst = self.rs2 - self.rs1
        self.assertTrue(rs_eq_array(rst, -truth))
        # Raster - scalar
        for v in [-1359, 0, 1, 2, 42]:
            truth = self.rs1_np - v
            rst = self.rs1.subtract(v)
            self.assertTrue(rs_eq_array(rst, truth))
            rst = self.rs1 - v
            self.assertTrue(rs_eq_array(rst, truth))
            rst = v - self.rs1
            self.assertTrue(rs_eq_array(rst, -truth))
        for v in [-1359.2, 0.0, 1.0, 2.0, 42.5]:
            truth = self.rs1_np - v
            rst = self.rs1.subtract(v)
            self.assertTrue(rs_eq_array(rst, truth))
            rst = self.rs1 - v
            self.assertTrue(rs_eq_array(rst, truth))
            rst = v - self.rs1
            self.assertTrue(rs_eq_array(rst, -truth))

    def test_mult(self):
        # Raster * raster
        truth = self.rs1_np * self.rs2_np
        rst = self.rs1.multiply(self.rs2)
        self.assertTrue(rs_eq_array(rst, truth))
        rst = self.rs2.multiply(self.rs1)
        self.assertTrue(rs_eq_array(rst, truth))
        rst = self.rs1 * self.rs2
        self.assertTrue(rs_eq_array(rst, truth))
        rst = self.rs2 * self.rs1
        self.assertTrue(rs_eq_array(rst, truth))
        # Raster * scalar
        for v in [-123, 0, 1, 2, 345]:
            truth = self.rs1_np * v
            rst = self.rs1.multiply(v)
            self.assertTrue(rs_eq_array(rst, truth))
            rst = self.rs1 * v
            self.assertTrue(rs_eq_array(rst, truth))
            rst = v * self.rs1
            self.assertTrue(rs_eq_array(rst, truth))
        for v in [-123.9, 0.0, 1.0, 2.0, 345.3]:
            truth = self.rs1_np * v
            rst = self.rs1.multiply(v)
            self.assertTrue(rs_eq_array(rst, truth))
            rst = self.rs1 * v
            self.assertTrue(rs_eq_array(rst, truth))
            rst = v * self.rs1
            self.assertTrue(rs_eq_array(rst, truth))

    def test_div(self):
        # Raster / raster
        truth = self.rs1_np / self.rs2_np
        rst = self.rs1.divide(self.rs2)
        self.assertTrue(rs_eq_array(rst, truth))
        rst = self.rs2.divide(self.rs1)
        self.assertTrue(rs_eq_array(rst, 1 / truth))
        rst = self.rs1 / self.rs2
        self.assertTrue(rs_eq_array(rst, truth))
        rst = self.rs2 / self.rs1
        self.assertTrue(rs_eq_array(rst, 1 / truth))
        # Raster / scalar, scalar / raster
        for v in [-123, -1, 1, 2, 345]:
            truth = self.rs1_np / v
            rst = self.rs1.divide(v)
            self.assertTrue(rs_eq_array(rst, truth))
            rst = self.rs1 / v
            self.assertTrue(rs_eq_array(rst, truth))
            rst = v / self.rs1
            np.testing.assert_array_almost_equal(rst.xrs.values, 1 / truth)
        for v in [-123.8, -1.0, 1.0, 2.0, 345.6]:
            truth = self.rs1_np / v
            rst = self.rs1.divide(v)
            self.assertTrue(rs_eq_array(rst, truth))
            rst = self.rs1 / v
            self.assertTrue(rs_eq_array(rst, truth))
            rst = v / self.rs1
            np.testing.assert_array_almost_equal(rst.xrs.values, 1 / truth)

    def test_mod(self):
        # Raster % raster
        truth = self.rs1_np % self.rs2_np
        rst = self.rs1.mod(self.rs2)
        self.assertTrue(rs_eq_array(rst, truth))
        rst = self.rs1 % self.rs2
        self.assertTrue(rs_eq_array(rst, truth))
        truth = self.rs2_np % self.rs1_np
        rst = self.rs2.mod(self.rs1)
        self.assertTrue(rs_eq_array(rst, truth))
        rst = self.rs2 % self.rs1
        self.assertTrue(rs_eq_array(rst, truth))
        # Raster % scalar, scalar % raster
        for v in [-123, -1, 1, 2, 345]:
            truth = self.rs1_np % v
            rst = self.rs1.mod(v)
            self.assertTrue(rs_eq_array(rst, truth))
            rst = self.rs1 % v
            self.assertTrue(rs_eq_array(rst, truth))
            truth = v % self.rs1_np
            rst = v % self.rs1
            self.assertTrue(rs_eq_array(rst, truth))
        for v in [-123.8, -1.0, 1.0, 2.0, 345.6]:
            truth = self.rs1_np % v
            rst = self.rs1.mod(v)
            self.assertTrue(rs_eq_array(rst, truth))
            rst = self.rs1 % v
            self.assertTrue(rs_eq_array(rst, truth))
            truth = v % self.rs1_np
            rst = v % self.rs1
            self.assertTrue(rs_eq_array(rst, truth))

    def test_power(self):
        # Raster ** raster
        rs1 = self.rs1 / self.rs1.xrs.max().values.item() * 2
        rs2 = self.rs2 / self.rs2.xrs.max().values.item() * 2
        rs1_np = self.rs1_np / self.rs1_np.max() * 2
        rs2_np = self.rs2_np / self.rs2_np.max() * 2
        truth = rs1_np ** rs2_np
        rst = rs1.pow(rs2)
        self.assertTrue(rs_eq_array(rst, truth))
        rst = rs2.pow(rs1)
        self.assertTrue(rs_eq_array(rst, truth))
        rst = rs1 ** rs2
        self.assertTrue(rs_eq_array(rst, truth))
        truth = rs2_np ** rs1_np
        rst = rs2 ** rs1
        self.assertTrue(rs_eq_array(rst, truth))
        # Raster ** scalar, scalar ** raster
        for v in [-10, -1, 1, 2, 11]:
            truth = rs1_np ** v
            rst = rs1.pow(v)
            self.assertTrue(rs_eq_array(rst, truth))
            rst = rs1 ** v
            self.assertTrue(rs_eq_array(rst, truth))
            # Avoid complex numbers issues
            if v >= 0:
                truth = v ** rs1_np
                rst = v ** rs1
                self.assertTrue(rs_eq_array(rst, truth))
        for v in [-10.5, -1.0, 1.0, 2.0, 11.3]:
            truth = rs1_np ** v
            rst = rs1.pow(v)
            self.assertTrue(rs_eq_array(rst, truth))
            rst = rs1 ** v
            self.assertTrue(rs_eq_array(rst, truth))
            # Avoid complex numbers issues
            if v >= 0:
                truth = v ** rs1_np
                rst = v ** rs1
                self.assertTrue(rs_eq_array(rst, truth))

    def test_sqrt(self):
        rs = self.rs1 + np.abs(self.rs1_np.min())
        rsnp = rs.xrs.values
        truth = np.sqrt(rsnp)
        self.assertTrue(rs_eq_array(rs.sqrt(), truth))


class TestLogicalOps(unittest.TestCase):
    def setUp(self):
        self.rs1 = Raster("tests/data/elevation_small.tif")
        self.rs1_np = self.rs1.xrs.values
        self.rs2 = Raster("tests/data/elevation2_small.tif")
        self.rs2_np = self.rs2.xrs.values

    def tearDown(self):
        self.rs1.close()
        self.rs2.close()

    def test_eq(self):
        for v, vnp in [
            (self.rs2, self.rs2_np),
            (0, 0),
            (self.rs1_np[0, 10, 10], self.rs1_np[0, 10, 10]),
        ]:
            truth = self.rs1_np == vnp
            rst = self.rs1.eq(v)
            self.assertTrue(rs_eq_array(rst, truth))
            rst = self.rs1 == v
            self.assertTrue(rs_eq_array(rst, truth))

    def test_ne(self):
        for v, vnp in [
            (self.rs2, self.rs2_np),
            (0, 0),
            (self.rs1_np[0, 10, 10], self.rs1_np[0, 10, 10]),
        ]:
            truth = self.rs1_np != vnp
            rst = self.rs1.ne(v)
            self.assertTrue(rs_eq_array(rst, truth))
            rst = self.rs1 != v
            self.assertTrue(rs_eq_array(rst, truth))

    def test_le(self):
        for v, vnp in [
            (self.rs2, self.rs2_np),
            (0, 0),
            (self.rs1_np[0, 10, 10], self.rs1_np[0, 10, 10]),
        ]:
            truth = self.rs1_np <= vnp
            rst = self.rs1.le(v)
            self.assertTrue(rs_eq_array(rst, truth))
            rst = self.rs1 <= v
            self.assertTrue(rs_eq_array(rst, truth))

    def test_ge(self):
        for v, vnp in [
            (self.rs2, self.rs2_np),
            (0, 0),
            (self.rs1_np[0, 10, 10], self.rs1_np[0, 10, 10]),
        ]:
            truth = self.rs1_np >= vnp
            rst = self.rs1.ge(v)
            self.assertTrue(rs_eq_array(rst, truth))
            rst = self.rs1 >= v
            self.assertTrue(rs_eq_array(rst, truth))

    def test_lt(self):
        for v, vnp in [
            (self.rs2, self.rs2_np),
            (0, 0),
            (self.rs1_np[0, 10, 10], self.rs1_np[0, 10, 10]),
        ]:
            truth = self.rs1_np < vnp
            rst = self.rs1.lt(v)
            self.assertTrue(rs_eq_array(rst, truth))
            rst = self.rs1 < v
            self.assertTrue(rs_eq_array(rst, truth))

    def test_gt(self):
        for v, vnp in [
            (self.rs2, self.rs2_np),
            (0, 0),
            (self.rs1_np[0, 10, 10], self.rs1_np[0, 10, 10]),
        ]:
            truth = self.rs1_np > vnp
            rst = self.rs1.gt(v)
            self.assertTrue(rs_eq_array(rst, truth))
            rst = self.rs1 > v
            self.assertTrue(rs_eq_array(rst, truth))


class TestAstype(unittest.TestCase):
    def test_astype(self):
        rs = Raster("tests/data/elevation_small.tif")
        for type_code, dtype in DTYPE_INPUT_TO_DTYPE.items():
            self.assertEqual(rs.astype(type_code).dtype, dtype)
            self.assertEqual(rs.astype(type_code).eval().dtype, dtype)
            self.assertEqual(rs.astype(dtype).dtype, dtype)
            self.assertEqual(rs.astype(dtype).eval().dtype, dtype)

    def test_wrong_type_codes(self):
        rs = Raster("tests/data/elevation_small.tif")
        with self.assertRaises(ValueError):
            rs.astype("not float32")
        with self.assertRaises(ValueError):
            rs.astype("other")

    def test_dtype_property(self):
        rs = Raster("tests/data/elevation_small.tif")
        self.assertEqual(rs.dtype, rs.xrs.dtype)

    def test_astype_str_uppercase(self):
        rs = Raster("tests/data/elevation_small.tif")
        for type_code, dtype in DTYPE_INPUT_TO_DTYPE.items():
            if isinstance(type_code, str):
                type_code = type_code.upper()
                self.assertEqual(rs.astype(type_code).eval().dtype, dtype)


class TestRasterAttrsPropagation(unittest.TestCase):
    def test_arithmetic_attrs(self):
        r1 = Raster("tests/data/elevation_small.tif")
        true_attrs = r1._attrs
        v = 2.1
        for op in _BINARY_ARITHMETIC_OPS.keys():
            r2 = r1._binary_arithmetic(v, op).eval()
            self.assertEqual(r2.xrs.attrs, true_attrs)
            self.assertEqual(r2._attrs, true_attrs)
        for r in [+r1, -r1]:
            self.assertEqual(r.xrs.attrs, true_attrs)
            self.assertEqual(r._attrs, true_attrs)

    def test_logical_attrs(self):
        r1 = Raster("tests/data/elevation_small.tif")
        true_attrs = r1._attrs
        v = 1.0
        for op in _BINARY_LOGICAL_OPS.keys():
            r2 = r1._binary_logical(v, op).eval()
            self.assertEqual(r2.xrs.attrs, true_attrs)
            self.assertEqual(r2._attrs, true_attrs)

    def test_ctor_attrs(self):
        r1 = Raster("tests/data/elevation_small.tif")
        true_attrs = r1._attrs.copy()
        r2 = Raster(Raster("tests/data/elevation_small.tif"))
        test_attrs = {"test": 0}
        r3 = Raster("tests/data/elevation_small.tif")
        r3._attrs = test_attrs
        self.assertEqual(r2._attrs, true_attrs)
        self.assertEqual(r3._attrs, test_attrs)

    def test_astype_attrs(self):
        rs = Raster("tests/data/elevation_small.tif")
        attrs = rs._attrs
        self.assertEqual(rs.astype(int)._attrs, attrs)

    def test_sqrt_attrs(self):
        rs = Raster("tests/data/elevation_small.tif")
        rs += np.abs(rs.xrs.values.min())
        attrs = rs._attrs
        self.assertEqual(rs.sqrt()._attrs, attrs)

    def test_log_attrs(self):
        rs = Raster("tests/data/elevation_small.tif")
        attrs = rs._attrs
        self.assertEqual(rs.log()._attrs, attrs)
        self.assertEqual(rs.log10()._attrs, attrs)

    def test_convolve_attrs(self):
        rs = Raster("tests/data/elevation_small.tif")
        attrs = rs._attrs
        self.assertEqual(focal.convolve(rs, np.ones((3, 3)))._attrs, attrs)

    def test_focal_attrs(self):
        rs = Raster("tests/data/elevation_small.tif")
        attrs = rs._attrs
        self.assertEqual(focal.focal(rs, "max", 3)._attrs, attrs)

    def test_band_concat_attrs(self):
        rs = Raster("tests/data/elevation_small.tif")
        attrs = rs._attrs
        rs2 = Raster("tests/data/elevation2_small.tif")
        self.assertEqual(band_concat([rs, rs2])._attrs, attrs)


class TestCopy(unittest.TestCase):
    def test_copy(self):
        rs = Raster("tests/data/elevation_small.tif")
        copy = rs.copy()
        self.assertIsNot(rs, copy)
        self.assertIsNot(rs.xrs, copy.xrs)
        self.assertIsNot(rs._attrs, copy._attrs)
        self.assertTrue((rs.xrs == copy.xrs).all())
        self.assertEqual(rs._attrs, copy._attrs)


class TestSetCrs(unittest.TestCase):
    def test_set_crs(self):
        rs = Raster("tests/data/elevation_small.tif")
        self.assertTrue(rs.crs != 4326)

        rs4326 = rs.set_crs(4326)
        self.assertTrue(rs4326.crs != rs.crs)
        self.assertTrue(rs4326.crs == 4326)
        self.assertTrue(np.allclose(rs._values, rs4326._values))


class TestSetNullValue(unittest.TestCase):
    def test_set_null_value(self):
        rs = Raster("tests/data/null_values.tiff")
        ndv = rs.null_value
        rs2 = rs.set_null_value(0)
        self.assertEqual(rs.null_value, ndv)
        self.assertEqual(rs._attrs["_FillValue"], ndv)
        self.assertEqual(rs2._attrs["_FillValue"], 0)

        rs = Raster("tests/data/elevation_small.tif")
        nv = rs.null_value
        rs2 = rs.set_null_value(None)
        self.assertEqual(rs.null_value, nv)
        self.assertEqual(rs._attrs["_FillValue"], nv)
        self.assertIsNone(rs2.null_value)
        self.assertIsNone(rs2._attrs["_FillValue"])


class TestReplaceNull(unittest.TestCase):
    def test_replace_null(self):
        fill_value = 0
        rs = Raster("tests/data/null_values.tiff")
        nv = rs.null_value
        rsnp = rs._values
        rsnp_replaced = rsnp.copy()
        rsnp_replaced[rsnp == rs.null_value] = fill_value
        rs = rs.replace_null(fill_value)
        self.assertTrue(np.allclose(rs._values, rsnp_replaced, equal_nan=True))
        self.assertEqual(rs.null_value, nv)
        self.assertTrue(rs._mask.sum().compute() == 0)


class TestWhere(unittest.TestCase):
    def test_where(self):
        rs = Raster("tests/data/elevation_small.tif")
        c = rs > 1100

        r = rs.where(c, 0)
        rsnp = np.asarray(rs)
        truth = np.where(rsnp > 1100, rsnp, 0)
        self.assertTrue(np.allclose(r, truth, equal_nan=True))
        self.assertTrue(
            np.allclose(
                rs.where(c, "tests/data/elevation_small.tif"),
                rs,
                equal_nan=True,
            )
        )

        c = c.astype(int)
        r = rs.where(c, 0)
        self.assertTrue(np.allclose(r, truth, equal_nan=True))

        self.assertTrue(rs._masked)
        self.assertTrue(r._masked)
        self.assertTrue(rs.crs is not None)
        self.assertTrue(r.crs == rs.crs)
        self.assertDictEqual(r._attrs, rs._attrs)

        with self.assertRaises(TypeError):
            cf = c.astype(float)
            rs.where(cf, 0)
        with self.assertRaises(TypeError):
            rs.where(c, None)


class TestToNullMask(unittest.TestCase):
    def test_to_null_mask(self):
        rs = Raster("tests/data/null_values.tiff")
        nv = rs.null_value
        rsnp = rs._values
        truth = rsnp == nv
        self.assertTrue(rs_eq_array(rs.to_null_mask(), truth))
        # Test case where no null values
        rs = Raster("tests/data/elevation_small.tif")
        truth = np.full(rs.shape, False, dtype=bool)
        self.assertTrue(rs_eq_array(rs.to_null_mask(), truth))


class TestEval(unittest.TestCase):
    def test_eval(self):
        rs = Raster("tests/data/elevation_small.tif")
        rsnp = rs.xrs.values
        rs += 2
        rsnp += 2
        rs -= rs
        rsnp -= rsnp
        rs *= -1
        rsnp *= -1
        result = rs.eval()
        # Make sure new raster returned
        self.assertIsNot(rs, result)
        self.assertIsNot(rs.xrs, result.xrs)
        # Make sure that original raster is still lazy
        self.assertTrue(dask.is_dask_collection(rs.xrs))
        self.assertTrue(rs_eq_array(result, rsnp))
        self.assertTrue(dask.is_dask_collection(result.xrs))
        # 2 operations: 1 copy and 1 chunk operation
        self.assertEqual(len(result._data.dask), 2)
        self.assertTrue(dask.is_dask_collection(result._mask))
        # 1 operation: dask.array.from_array()
        self.assertTrue(len(result._mask.dask), 1)


class TestToDask(unittest.TestCase):
    def test_to_dask(self):
        rs = Raster("tests/data/elevation2_small.tif")
        self.assertTrue(isinstance(rs.to_dask(), dask.array.Array))
        self.assertIs(rs.to_dask(), rs._data)
        self.assertTrue(isinstance(rs.eval().to_dask(), dask.array.Array))


class TestAndOr(unittest.TestCase):
    def test_and(self):
        rs1 = Raster("tests/data/elevation_small.tif")
        rsnp1 = rs1.xrs.values
        rs2 = Raster("tests/data/elevation2_small.tif")
        rsnp2 = rs2.xrs.values
        rsnp2 -= rsnp2.max() / 2
        truth = (rsnp1 > 0) & (rsnp2 > 0)
        self.assertTrue(rs_eq_array(rs1 & rs2, truth))
        self.assertTrue(rs_eq_array(rs1.and_(rs2), truth))
        truth = rsnp1.astype(bool) & rsnp2.astype(bool)
        self.assertTrue(rs_eq_array(rs1.and_(rs2, "cast"), truth))
        for v in [-22.0, -20, 0, 1, 1.0, 23.1, 30]:
            truth = (rsnp1 > 0) & (v > 0)
            self.assertTrue(rs_eq_array(rs1 & v, truth))
            self.assertTrue(rs_eq_array(rs1.and_(v), truth))
            truth = rsnp1.astype(bool) & bool(v)
            self.assertTrue(rs_eq_array(rs1.and_(v, "cast"), truth))
        for v in [False, True]:
            truth = (rsnp1 > 0) & v
            self.assertTrue(rs_eq_array(rs1 & v, truth))
            self.assertTrue(rs_eq_array(rs1.and_(v), truth))
            truth = rsnp1.astype(bool) & v
            self.assertTrue(rs_eq_array(rs1.and_(v, "cast"), truth))

    def test_or(self):
        rs1 = Raster("tests/data/elevation_small.tif")
        rsnp1 = rs1.xrs.values
        rs2 = Raster("tests/data/elevation2_small.tif")
        rsnp2 = rs2.xrs.values
        rsnp2 -= rsnp2.max() / 2
        truth = (rsnp1 > 0) | (rsnp2 > 0)
        self.assertTrue(rs_eq_array(rs1 | rs2, truth))
        self.assertTrue(rs_eq_array(rs1.or_(rs2), truth))
        truth = rsnp1.astype(bool) | rsnp2.astype(bool)
        self.assertTrue(rs_eq_array(rs1.or_(rs2, "cast"), truth))
        for v in [-22.0, -20, 0, 1, 1.0, 23.1, 30]:
            truth = (rsnp1 > 0) | (v > 0)
            self.assertTrue(rs_eq_array(rs1 | v, truth))
            self.assertTrue(rs_eq_array(rs1.or_(v), truth))
            truth = rsnp1.astype(bool) | bool(v)
            self.assertTrue(rs_eq_array(rs1.or_(v, "cast"), truth))
        for v in [False, True]:
            truth = (rsnp1 > 0) | v
            self.assertTrue(rs_eq_array(rs1 | v, truth))
            self.assertTrue(rs_eq_array(rs1.or_(v), truth))
            truth = rsnp1.astype(bool) | v
            self.assertTrue(rs_eq_array(rs1.or_(v, "cast"), truth))


class TestBitwiseComplement(unittest.TestCase):
    def test_invert(self):
        ar = np.array([[0, 1], [1, 0]])
        bool_ar = ar.astype(bool)
        inv_bool_ar = np.array([[1, 0], [0, 1]], dtype=bool)

        rs = Raster(bool_ar)
        rs_inv = Raster(inv_bool_ar)
        self.assertTrue(rs_eq_array(~rs, inv_bool_ar))
        self.assertTrue(rs_eq_array(~rs_inv, bool_ar))
        self.assertTrue(rs_eq_array(~Raster(ar), ~ar))

    def test_invert_errors(self):
        ar = np.array([[0, 1], [1, 0]], dtype=float)
        rs = Raster(ar)
        with self.assertRaises(TypeError):
            ~rs


class TestGetBands(unittest.TestCase):
    def test_get_bands(self):
        rs = Raster("tests/data/multiband_small.tif")
        rsnp = rs.xrs.values
        self.assertTrue(rs_eq_array(rs.get_bands(1), rsnp[:1]))
        self.assertTrue(rs_eq_array(rs.get_bands(2), rsnp[1:2]))
        self.assertTrue(rs_eq_array(rs.get_bands(3), rsnp[2:3]))
        self.assertTrue(rs_eq_array(rs.get_bands(4), rsnp[3:4]))
        for bands in [[1], [1, 2], [1, 1], [3, 1, 2], [4, 3, 2, 1]]:
            np_bands = [i - 1 for i in bands]
            result = rs.get_bands(bands)
            self.assertTrue(np.allclose(result, rsnp[np_bands]))
            bnd_dim = list(range(1, len(bands) + 1))
            self.assertTrue(np.allclose(result.xrs.band, bnd_dim))

        self.assertTrue(len(rs.get_bands(1).shape) == 3)

        for bands in [0, 5, [1, 5], [0]]:
            with self.assertRaises(IndexError):
                rs.get_bands(bands)
        with self.assertRaises(ValueError):
            rs.get_bands([])


if __name__ == "__main__":
    unittest.main()
