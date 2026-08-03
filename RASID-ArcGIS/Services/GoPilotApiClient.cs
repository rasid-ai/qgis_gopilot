using System.Collections.Generic;
using System.IO;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using System.Threading.Tasks;
using Rasid.Models;

namespace Rasid.Services
{
	internal class GoPilotApiClient
	{
		private readonly ApiClient _api;
		public GoPilotApiClient(ApiClient api) { _api = api; }

		
		public Task<ChatSession> CreateSessionAsync(string title = "New Chat") =>
			PostAt<ChatSession>("sessions/", new { title });

		
		public Task<JsonElement> GetSessionHistoryAsync() => GetAt<JsonElement>("sessions/history/");

		
		public Task<JsonElement> GetSessionAsync(int sessionId) =>
			GetAt<JsonElement>($"sessions/{sessionId}/");

		
		public async Task DeleteSessionAsync(int sessionId)
		{
			using var response = await _api.Raw.DeleteAsync(
				_api.GoPilotBaseUrl + $"sessions/{sessionId}/");
			response.EnsureSuccessStatusCode();
		}

		
		public async Task<JsonElement> SendMessageAsync(int sessionId, string content,
			object inputMetadata = null, List<string> filePaths = null,
			string geoJsonData = null)
		{
			using var form = new MultipartFormDataContent { { new StringContent(content), "content" } };
			if (inputMetadata != null)
				form.Add(new StringContent(JsonSerializer.Serialize(inputMetadata)), "input_metadata");
			if (!string.IsNullOrWhiteSpace(geoJsonData))
				form.Add(new StringContent(geoJsonData), "geojson_data");

			if (filePaths != null)
			{
				foreach (var path in filePaths)
				{
					var bytes = await File.ReadAllBytesAsync(path);
					form.Add(new ByteArrayContent(bytes), "files", Path.GetFileName(path));
				}
			}

			var response = await _api.Raw.PostAsync(
				_api.GoPilotBaseUrl + $"sessions/{sessionId}/send_message/", form);
			response.EnsureSuccessStatusCode();
			return await response.Content.ReadFromJsonAsync<JsonElement>();
		}

		
		public Task<List<ChatMessage>> GetMessagesAsync(int sessionId) =>
			GetAt<List<ChatMessage>>($"sessions/{sessionId}/messages/");

		
		public Task<GoPilotTaskStatus> GetTaskStatusAsync(string taskId) =>
			GetAt<GoPilotTaskStatus>($"sessions/tasks/{taskId}/");

		
		public Task<JsonElement> GetUserFilesAsync() => GetAt<JsonElement>("files/user_files/");

		
		public Task<JsonElement> GetFileAsync(int fileId) => GetAt<JsonElement>($"files/{fileId}/");

		
		public Task<JsonElement> DeleteFileAsync(int fileId) =>
			PostAt<JsonElement>($"files/{fileId}/delete_file/", null, isDelete: true);

		
		public Task<JsonElement> CheckFileProcessingStatusAsync(int fileId) =>
			GetAt<JsonElement>($"files/{fileId}/check_processing_status/");

		
		public Task<JsonElement> RetryFileProcessingAsync(int fileId) =>
			PostAt<JsonElement>($"files/{fileId}/retry_processing/", new { });

		private async Task<T> GetAt<T>(string path)
		{
			var response = await _api.Raw.GetAsync(_api.GoPilotBaseUrl + path);
			response.EnsureSuccessStatusCode();

			
			var rawJson = await response.Content.ReadAsStringAsync();
			
			return System.Text.Json.JsonSerializer.Deserialize<T>(rawJson);
		}

		private async Task<T> PostAt<T>(string path, object payload, bool isDelete = false)
		{
			var response = isDelete
				? await _api.Raw.DeleteAsync(_api.GoPilotBaseUrl + path)
				: await _api.Raw.PostAsJsonAsync(_api.GoPilotBaseUrl + path, payload);
			response.EnsureSuccessStatusCode();
			return await response.Content.ReadFromJsonAsync<T>();
		}
	}
}
