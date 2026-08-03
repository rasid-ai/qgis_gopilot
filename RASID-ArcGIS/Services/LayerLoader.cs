using ArcGIS.Desktop.Core;
using ArcGIS.Desktop.Core.Geoprocessing;
using ArcGIS.Desktop.Framework.Threading.Tasks;
using ArcGIS.Desktop.Mapping;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using System.Threading.Tasks;

namespace Rasid.Services
{
	internal static class LayerLoader
	{
		public static bool LayerExists(string layerName) =>
			MapView.Active?.Map.GetLayersAsFlattenedList()
				.Any(layer => layer.Name == layerName) ?? false;

		public static async Task LoadResultAsync(
			string filepath,
			string layerName)
		{
			if (string.IsNullOrWhiteSpace(filepath) || !System.IO.File.Exists(filepath))
				throw new System.IO.FileNotFoundException(
					"The downloaded layer file was not found.", filepath);

			if (Path.GetExtension(filepath).Equals(
				".geojson",
				System.StringComparison.OrdinalIgnoreCase))
			{
				filepath = await ConvertGeoJsonAsync(filepath, layerName);
			}

			var mapView = MapView.Active;
			if (mapView?.Map == null)
			{
				throw new System.InvalidOperationException(
					"Open a map in ArcGIS Pro before loading this result.");
			}

			var loaded = await QueuedTask.Run(() =>
			{
				var map = mapView.Map;
				var group = map.GetLayersAsFlattenedList()
					.OfType<GroupLayer>()
					.FirstOrDefault(layer => layer.Name == "RASID")
					?? LayerFactory.Instance.CreateGroupLayer(
						map,
						0,
						"RASID");

				var layer = LayerFactory.Instance.CreateLayer(
					new System.Uri(filepath),
					group,
					layerName: layerName);

				return layer != null && group.Layers.Contains(layer);
			});

			if (!loaded)
				throw new System.InvalidOperationException(
					$"ArcGIS Pro could not open '{System.IO.Path.GetFileName(filepath)}' as a layer.");
		}

		private static async Task<string> ConvertGeoJsonAsync(
			string filepath,
			string layerName)
		{
			var geodatabasePath = Project.Current?.DefaultGeodatabasePath;
			if (string.IsNullOrWhiteSpace(geodatabasePath))
				throw new System.InvalidOperationException(
					"The ArcGIS Pro project does not have a default geodatabase.");

			var safeName = Regex.Replace(
				layerName ?? "gopilot_result",
				@"[^A-Za-z0-9_]",
				"_");
			if (string.IsNullOrWhiteSpace(safeName))
				safeName = "gopilot_result";
			if (char.IsDigit(safeName[0]))
				safeName = "_" + safeName;

			var outputPath = Path.Combine(
				geodatabasePath,
				$"{safeName}_{System.DateTime.UtcNow:yyyyMMddHHmmssfff}");
			var result = await Geoprocessing.ExecuteToolAsync(
				"conversion.JSONToFeatures",
				Geoprocessing.MakeValueArray(filepath, outputPath),
				null,
				null,
				GPExecuteToolFlags.None);

			if (result.IsFailed)
				throw new System.InvalidOperationException(
					"ArcGIS Pro could not convert the GeoJSON file to a feature class.");

			return outputPath;
		}
	}
}
