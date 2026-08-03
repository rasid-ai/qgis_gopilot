#nullable enable annotations

using ArcGIS.Desktop.Framework;
using Rasid.Models;
using Rasid.Pages.Base;
using Rasid.Services;
using Rasid.Services.Geometry;
using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using System.Windows.Input;
using System.Windows.Media.Imaging;
using ArcGIS.Core.Geometry;
using ArcGIS.Desktop.Framework.Threading.Tasks;
using ArcGIS.Desktop.Mapping;
namespace Rasid.Pages.GoPilot
{
    internal class GoPilotViewModel : PageViewModelBase, IDisposable
    {
        private readonly GoPilotApiClient _gopilot;
        private readonly RasidApiClient _rasidApi;
        private readonly GeometryInputManager _geoManager;
        private readonly HashSet<int> _deletingSessionIds = new();
        private int? _sessionId;
        private bool _suppressSessionSelection;

        public ObservableCollection<ChatMessage> Messages { get; }
    = new ObservableCollection<ChatMessage>();

        public ObservableCollection<ChatSession> Sessions { get; } = new();

        private string _draftText;
        public string DraftText
        {
            get => _draftText;
            set
            {
                SetProperty(ref _draftText, value);
                NotifyPropertyChanged(nameof(CanSend));
            }
        }

        private string _statusText = "Ready";
        public string StatusText
        {
            get => _statusText;
            set => SetProperty(ref _statusText, value);
        }

        private string _historyStatus;
        public string HistoryStatus
        {
            get => _historyStatus;
            set => SetProperty(ref _historyStatus, value);
        }
        private Polygon? _selectedAoi;

        public Polygon? SelectedAoi
        {
            get => _selectedAoi;
            private set
            {
                _selectedAoi = value;
                NotifyPropertyChanged();
                NotifyPropertyChanged(nameof(HasSelectedAoi));
            }
        }
        private async Task DrawAoiAsync()
        {
            AoiSketchTool.PolygonFinished -= OnPolygonFinished;
            AoiSketchTool.PolygonFinished += OnPolygonFinished;

            await FrameworkApplication.SetCurrentToolAsync(
                "Rasid_AoiSketchTool");
        }

        private void OnPolygonFinished(Polygon polygon)
        {
            AoiSketchTool.PolygonFinished -= OnPolygonFinished;

            SelectedAoi = polygon;

            var areaKm2 = CalculateAreaKm2(polygon);
            var pointCount = polygon.PointCount;

            System.Windows.Application.Current.Dispatcher.Invoke(() =>
            {
                Messages.Add(new ChatMessage
                {
                    IsUser = true,
                    Text = "Area selected from map",
                    IsAoiAttachment = true,
                    AoiTitle = "Selected area",
                    AoiDetails =
                        $"{areaKm2:N2} km² · {pointCount} vertices"
                });
            });
        }
        private static double CalculateAreaKm2(
    ArcGIS.Core.Geometry.Polygon polygon)
        {
            return Math.Abs(
                GeometryEngine.Instance.GeodesicArea(
                    polygon,
                    AreaUnit.SquareKilometers));
        }
        private bool _isAoiAttachment;

        public bool IsAoiAttachment
        {
            get => _isAoiAttachment;
            set
            {
                _isAoiAttachment = value;
                NotifyPropertyChanged();
            }
        }

        public string? AoiTitle { get; set; }

        public string? AoiDetails { get; set; }
        public bool HasSelectedAoi => SelectedAoi != null;
        private bool _isBusy;
        public bool IsBusy
        {
            get => _isBusy;
            set
            {
                SetProperty(ref _isBusy, value);
                NotifyPropertyChanged(nameof(CanSend));
            }
        }

        public bool CanSend => !IsBusy && !string.IsNullOrWhiteSpace(DraftText);
        public bool HasMessages => Messages.Count > 0;

        private ChatSession _selectedSession;
        public ChatSession SelectedSession
        {
            get => _selectedSession;
            set
            {
                if (ReferenceEquals(_selectedSession, value))
                    return;

                SetProperty(ref _selectedSession, value);
                if (!_suppressSessionSelection && value != null)
                    _ = OpenSessionAsync(value);
            }
        }

        private string _attachedGeoJson;
        private string _attachmentSourceName;

        public bool HasAttachment => !string.IsNullOrWhiteSpace(_attachedGeoJson);

        public string AttachmentStatusText => IsLayerActive || IsDrawActive
            ? "Preparing geometry..."
            : !string.IsNullOrWhiteSpace(_attachmentSourceName)
                ? $"Attached: {_attachmentSourceName}"
                : "Geometry attached ✓";

        private bool _isDrawActive;
        public bool IsDrawActive
        {
            get => _isDrawActive;
            set
            {
                SetProperty(ref _isDrawActive, value);
                NotifyPropertyChanged(nameof(AttachmentStatusText));
            }
        }

        private bool _isLayerActive;
        public bool IsLayerActive
        {
            get => _isLayerActive;
            set
            {
                SetProperty(ref _isLayerActive, value);
                NotifyPropertyChanged(nameof(AttachmentStatusText));
            }
        }

        public ICommand SendCommand { get; }
        public ICommand DrawCommand { get; }
        public ICommand PickLayerCommand { get; }
        public ICommand ClearAttachmentCommand { get; }
        public ICommand NewChatCommand { get; }
        public ICommand RefreshHistoryCommand { get; }
        public ICommand DeleteSessionCommand { get; }
        public ICommand DownloadFileCommand { get; }

        public GoPilotViewModel()
        {
            _gopilot = new GoPilotApiClient(ApiClient.Instance);
            _rasidApi = new RasidApiClient(ApiClient.Instance);
            _geoManager = new GeometryInputManager();
            _geoManager.GeometryReady += OnGeometryReady;
            _geoManager.DrawCancelled += OnDrawCancelled;

            SendCommand = new RelayCommand(async () => await SendMessageAsync());
            DrawCommand = new RelayCommand(async () => await StartDrawGeometryAsync());
            PickLayerCommand = new RelayCommand(async () => await PickLayerAsync());
            ClearAttachmentCommand = new RelayCommand(ClearAttachedGeometry);
            NewChatCommand = new RelayCommand(StartNewChat);
            RefreshHistoryCommand = new RelayCommand(async () => await LoadSessionHistoryAsync());
            DeleteSessionCommand = new RelayCommand(
                async parameter => await DeleteSessionAsync(parameter),
                _ => true,
                true,
                true);
            DownloadFileCommand = new RelayCommand(
                async parameter => await HandleFileAsync(parameter),
                _ => true,
                true,
                true);

            _ = LoadSessionHistoryAsync();
        }

        private void StartNewChat()
        {
            _sessionId = null;
            _suppressSessionSelection = true;
            SelectedSession = null;
            _suppressSessionSelection = false;
            Messages.Clear();
            NotifyPropertyChanged(nameof(HasMessages));
            ClearAttachedGeometry();
            StatusText = "Ready";
        }

        private async Task LoadSessionHistoryAsync()
        {
            try
            {
                HistoryStatus = "Loading history...";
                var history = await _gopilot.GetSessionHistoryAsync();
                var items = ResolveSessionArray(history);

                Sessions.Clear();
                if (items.ValueKind == JsonValueKind.Array)
                {
                    int totalSessions = 0;
                    int loadedSessions = 0;

                    foreach (var item in items.EnumerateArray())
                    {
                        totalSessions++;
                        try
                        {
                            var session = JsonSerializer.Deserialize<ChatSession>(item.GetRawText());
                            if (session != null)
                            {
                                Sessions.Add(session);
                                loadedSessions++;

                            }
                        }
                        catch (Exception ex)
                        {
                            System.Diagnostics.Debug.WriteLine($"  [!] Failed to parse session: {ex.Message}");
                        }
                    }


                }
                else
                {
                    System.Diagnostics.Debug.WriteLine($"  • WARNING: Items is not an array!");
                }


                HistoryStatus = Sessions.Count == 0 ? "No previous chats." : null;
            }
            catch (Exception ex)
            {

                HistoryStatus = $"History unavailable: {ex.Message}";
            }
        }

        private static JsonElement ResolveSessionArray(JsonElement history)
        {
            if (history.ValueKind == JsonValueKind.Array)
                return history;

            if (history.ValueKind == JsonValueKind.Object)
            {
                foreach (var key in new[] { "results", "sessions", "history" })
                    if (history.TryGetProperty(key, out var value) && value.ValueKind == JsonValueKind.Array)
                        return value;
            }

            return default;
        }

        private async Task OpenSessionAsync(ChatSession session)
        {
            if (session == null || _deletingSessionIds.Contains(session.Id))
                return;

            var ownsBusyState = !IsBusy;
            if (ownsBusyState)
                IsBusy = true;
            StatusText = "Loading chat...";
            try
            {
                _sessionId = session.Id;
                var messages = await _gopilot.GetMessagesAsync(session.Id);

                // The user may delete the row while its messages are loading.
                if (_deletingSessionIds.Contains(session.Id) ||
                    !Sessions.Contains(session) ||
                    SelectedSession?.Id != session.Id)
                    return;

                Messages.Clear();
                if (messages != null)
                {
                    int index = 1;
                    foreach (var message in messages)
                    {
                        message.UseHistoricalTimestamp = true;
                        PrepareMessageFiles(message);
                        Messages.Add(message);
                        System.Diagnostics.Debug.WriteLine($"  [{index}] Role: {message.Role}, Text Length: {message.Text?.Length ?? 0}, Time: {message.Timestamp:HH:mm:ss}");
                        if (!string.IsNullOrEmpty(message.Text) && message.Text.Length > 0)
                        {
                            var preview = message.Text.Length > 50
                                ? message.Text.Substring(0, 50) + "..."
                                : message.Text;

                        }
                        index++;
                    }
                }



                NotifyPropertyChanged(nameof(HasMessages));
                StatusText = "Ready";
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"[GOPILOT DEBUG] ERROR loading messages: {ex.Message}");
                StatusText = $"Could not load chat: {ex.Message}";
            }
            finally
            {
                if (ownsBusyState)
                    IsBusy = false;
            }
        }

        private async Task DeleteSessionAsync(object parameter)
        {
            if (parameter is not ChatSession session)
                return;

            var result = ArcGIS.Desktop.Framework.Dialogs.MessageBox.Show(
                $"Delete the chat \"{session.Title}\"?\n\nThis action cannot be undone.",
                "Delete Chat",
                System.Windows.MessageBoxButton.YesNo,
                System.Windows.MessageBoxImage.Warning);

            if (result != System.Windows.MessageBoxResult.Yes)
                return;

            if (!_deletingSessionIds.Add(session.Id))
                return;

            try
            {
                await _gopilot.DeleteSessionAsync(session.Id);

                var deletedCurrentSession = _sessionId == session.Id;
                Sessions.Remove(session);

                if (deletedCurrentSession)
                {
                    _sessionId = null;
                    _suppressSessionSelection = true;
                    SelectedSession = null;
                    _suppressSessionSelection = false;
                    Messages.Clear();
                    ClearAttachedGeometry();
                    NotifyPropertyChanged(nameof(HasMessages));
                    StatusText = "Ready";
                }

                HistoryStatus = Sessions.Count == 0
                    ? "No previous chats."
                    : null;
            }
            catch (Exception ex)
            {
                ArcGIS.Desktop.Framework.Dialogs.MessageBox.Show(
                    $"Could not delete the chat:\n{ex.Message}",
                    "Delete Failed");
            }
            finally
            {
                _deletingSessionIds.Remove(session.Id);
            }
        }

        private async Task StartDrawGeometryAsync()
        {
            IsDrawActive = true;
            StatusText =
                "Draw on map (right-click, Enter, or F2 to finish).";
            try
            {
                var started = await _geoManager.StartDrawModeAsync(helpContext: "gopilot");
                if (!started)
                {
                    IsDrawActive = false;
                    StatusText = "Ready";
                }
            }
            catch (Exception ex)
            {
                IsDrawActive = false;
                StatusText = $"Drawing failed: {ex.Message}";
            }
        }

        private async Task PickLayerAsync()
        {
            IsLayerActive = true;
            StatusText = "Select a layer...";
            try
            {
                var selected = await _geoManager.ShowLayerPickerAsync(title: "Select Layer");
                if (!selected)
                {
                    IsLayerActive = false;
                    StatusText = "Ready";
                }
            }
            catch (Exception ex)
            {
                IsLayerActive = false;
                StatusText = $"Layer selection failed: {ex.Message}";
            }
        }
        private void OnGeometryReady(GeoJsonResult result)
        {
            _attachedGeoJson = result.GeoJson;
            _attachmentSourceName = result.Source == "draw" ? "Drawn geometry" : result.Name;
            IsDrawActive = false;
            IsLayerActive = false;
            StatusText = result.Source == "draw"
                ? "Geometry attached ✓"
                : $"Layer '{result.Name}' attached ✓";

            NotifyPropertyChanged(nameof(HasAttachment));
            NotifyPropertyChanged(nameof(AttachmentStatusText));
        }

        private void OnDrawCancelled()
        {
            IsDrawActive = false;
            if (!IsBusy)
                StatusText = "Drawing cancelled";
        }

        private void ClearAttachedGeometry()
        {
            _attachedGeoJson = null;
            _attachmentSourceName = null;
            AoiSketchTool.ClearAoiOverlay();
            IsDrawActive = false;
            IsLayerActive = false;
            if (!IsBusy)
                StatusText = "Ready";

            NotifyPropertyChanged(nameof(HasAttachment));
            NotifyPropertyChanged(nameof(AttachmentStatusText));
        }
        private void RefreshMessage(ChatMessage message)
        {
            var index = Messages.IndexOf(message);

            if (index < 0)
                return;

            Messages.RemoveAt(index);
            Messages.Insert(index, message);
        }
        private async Task SendMessageAsync()
        {
            if (!CanSend)
                return;

            var text = DraftText.Trim();
            var attachedGeoJson = _attachedGeoJson;
            var hasAttachment = !string.IsNullOrWhiteSpace(attachedGeoJson);
            string tempPath = null;
            int? requestSessionId = _sessionId;


            IsBusy = true;
            Messages.Add(new ChatMessage
            {
                IsUser = true,
                Content = text,
                SystemRegistrationDate = DateTime.Now,
                AttachmentPath = hasAttachment ? "geometry" : null
            });
            DraftText = string.Empty;

            var thinking = new ChatMessage
            {
                IsUser = false,
                IsPending = true,
                SystemRegistrationDate = DateTime.Now
            };
            Messages.Add(thinking);
            NotifyPropertyChanged(nameof(HasMessages));

            System.Diagnostics.Debug.WriteLine($"  • Total Messages in Conversation: {Messages.Count}");

            try
            {
                object inputMetadata = null;
                List<string> filesToUpload = null;
                if (hasAttachment)
                {
                    inputMetadata = new { type = "vector_upload", format = "geojson" };
                    tempPath = Path.Combine(Path.GetTempPath(), $"rasid_geometry_{Guid.NewGuid():N}.geojson");
                    await File.WriteAllTextAsync(tempPath, attachedGeoJson);
                    filesToUpload = new List<string> { tempPath };
                    System.Diagnostics.Debug.WriteLine($"  • GeoJSON saved to temp: {tempPath}");
                }

                ClearAttachedGeometry();

                if (requestSessionId is null)
                {
                    StatusText = "Creating chat...";
                    var session = await _gopilot.CreateSessionAsync("New Chat");
                    requestSessionId = session.Id;
                    if (_sessionId is null)
                        _sessionId = session.Id;
                    System.Diagnostics.Debug.WriteLine($"  • New Session Created: ID={_sessionId}");
                }

                if (_sessionId == requestSessionId)
                    StatusText = "Sending message...";
                var result = await _gopilot.SendMessageAsync(
                    requestSessionId.Value,
                    text,
                    inputMetadata,
                    filesToUpload,
                    attachedGeoJson);
                var taskId = result.GetProperty("task").GetProperty("task_id").GetString();
                if (string.IsNullOrWhiteSpace(taskId))
                    throw new InvalidOperationException("The server response did not contain a task ID.");

                await PollTaskAsync(taskId, thinking, requestSessionId.Value);
                if (_sessionId == requestSessionId)
                {
                    await LoadCompletedSessionAsync(requestSessionId.Value);
                    await LoadSessionHistoryAsync();
                    NotifyPropertyChanged(nameof(HasMessages));
                }
            }
            catch (Exception ex)
            {

                thinking.IsPending = false;
                thinking.Text = $"Error: {ex.Message}";
                thinking.SystemRegistrationDate = DateTime.Now;
                if (_sessionId == requestSessionId)
                {
                    StatusText = "Error sending message";
                    RefreshLastMessage();
                }
            }
            finally
            {
                IsBusy = false;
                if (!string.IsNullOrEmpty(tempPath))
                {
                    try { File.Delete(tempPath); } catch { }
                }
            }
        }

        private async Task PollTaskAsync(
            string taskId,
            ChatMessage pendingReply,
            int sessionId)
        {
            var pollInterval = TimeSpan.FromSeconds(2);

            if (_sessionId == sessionId)
                StatusText = "GoPilot is thinking...";

            while (true)
            {
                var task = await _gopilot.GetTaskStatusAsync(taskId);
                var currentText = task.LlmMessage?.Content ?? task.ResultText;
                var isProcessing = task.LlmGenerating || task.FilesProcessing;
                await System.Windows.Application.Current.Dispatcher
                    .InvokeAsync(() =>
                    {
                        if (_sessionId != sessionId)
                            return;

                        if (currentText != null)
                            pendingReply.Text = task.FilesProcessing
                                ? GoPilotFileLinkParser.HideFilesWhileProcessing(currentText)
                                : currentText;

                        pendingReply.IsPending =
                            isProcessing &&
                            string.IsNullOrWhiteSpace(pendingReply.Text);

						if (task.FilesProcessing && !task.LlmGenerating)
						{
							StatusText = "Files are processing...";
						}
						else if (isProcessing)
                        {
                            StatusText = "GoPilot is processing...";
                        }
                        else
                        {
                            pendingReply.SystemRegistrationDate = DateTime.Now;
                            PrepareMessageFiles(pendingReply);
                            StatusText = "Ready";
                        }

                        RefreshMessage(pendingReply);
                    });

                if (!isProcessing)
                {
                    return;
                }

                await Task.Delay(pollInterval);
            }
        }

        private async Task LoadCompletedSessionAsync(int sessionId)
        {
            var localUserTimestamp = Messages
                .LastOrDefault(message => message.IsUser)?
                .SystemRegistrationDate;
            var localReplyTimestamp = Messages
                .LastOrDefault(message => !message.IsUser)?
                .SystemRegistrationDate;
            var session = await _gopilot.GetSessionAsync(sessionId);
            var messageArray = ResolveMessageArray(session);

            if (messageArray.ValueKind != JsonValueKind.Array)
                throw new InvalidOperationException(
                    "The completed session response did not contain a message list.");

            var messages = new List<ChatMessage>();
            foreach (var item in messageArray.EnumerateArray())
            {
                var message = JsonSerializer.Deserialize<ChatMessage>(
                    item.GetRawText());
                if (message != null)
                {
                    message.UseHistoricalTimestamp = true;
                    PrepareMessageFiles(message);
                    messages.Add(message);
                }
            }

            var newestUser = messages.LastOrDefault(message => message.IsUser);
            if (newestUser != null && localUserTimestamp.HasValue)
            {
                newestUser.SystemRegistrationDate = localUserTimestamp.Value;
                newestUser.UseHistoricalTimestamp = false;
            }

            var newestReply = messages.LastOrDefault(message => !message.IsUser);
            if (newestReply != null && localReplyTimestamp.HasValue)
            {
                newestReply.SystemRegistrationDate = localReplyTimestamp.Value;
                newestReply.UseHistoricalTimestamp = false;
            }

            await System.Windows.Application.Current.Dispatcher.InvokeAsync(() =>
            {
                Messages.Clear();
                foreach (var message in messages)
                    Messages.Add(message);

                NotifyPropertyChanged(nameof(HasMessages));
                StatusText = "Ready";
            });
        }

        private static JsonElement ResolveMessageArray(JsonElement session)
        {
            if (session.ValueKind == JsonValueKind.Array)
                return session;

            if (session.ValueKind != JsonValueKind.Object)
                return default;

            if (session.TryGetProperty("messages", out var messages) &&
                messages.ValueKind == JsonValueKind.Array)
                return messages;

            foreach (var key in new[] { "session", "data", "result" })
            {
                if (session.TryGetProperty(key, out var nested))
                {
                    var nestedMessages = ResolveMessageArray(nested);
                    if (nestedMessages.ValueKind == JsonValueKind.Array)
                        return nestedMessages;
                }
            }

            return default;
        }

        private void PrepareMessageFiles(ChatMessage message)
        {
            message.Files.Clear();
            if (message.IsUser || string.IsNullOrWhiteSpace(message.Text))
                return;

            foreach (var file in GoPilotFileLinkParser.Extract(message.Text))
            {
                message.Files.Add(file);
                if (file.IsImage)
                    _ = LoadImagePreviewAsync(file);
            }
        }

        private async Task LoadImagePreviewAsync(ChatFileAttachment file)
        {
            file.PreviewStatus = $"Loading {file.FileName}...";
            try
            {
                var localPath = File.Exists(file.LocalPath)
                    ? file.LocalPath
                    : await _rasidApi.DownloadFileAsync(file.Url);
                var imageBytes = await File.ReadAllBytesAsync(localPath);

                await System.Windows.Application.Current.Dispatcher.InvokeAsync(() =>
                {
                    using var stream = new MemoryStream(imageBytes);
                    var bitmap = new BitmapImage();
                    bitmap.BeginInit();
                    bitmap.CacheOption = BitmapCacheOption.OnLoad;
                    bitmap.StreamSource = stream;
                    bitmap.EndInit();
                    bitmap.Freeze();

                    file.LocalPath = localPath;
                    file.Preview = bitmap;
                    file.PreviewStatus = null;
                });
            }
            catch (Exception ex)
            {
                file.PreviewStatus =
                    $"Preview unavailable: {ex.Message}";
            }
        }

        private async Task HandleFileAsync(object parameter)
        {
            if (parameter is not ChatFileAttachment file ||
                !file.IsActionEnabled)
                return;

            file.IsActionEnabled = false;
            try
            {
                if (file.IsImage)
                {
                    await SaveImageAsync(file);
                    return;
                }

                file.ActionText = $"Downloading {file.FileName}...";
                var localPath = File.Exists(file.LocalPath)
                    ? file.LocalPath
                    : await _rasidApi.DownloadFileAsync(file.Url);
                file.LocalPath = localPath;

				var downloadedExtension = Path.GetExtension(localPath).TrimStart('.');
				if (!string.IsNullOrWhiteSpace(downloadedExtension))
				{
					file.FileName = Path.GetFileName(localPath);
					file.Extension = downloadedExtension.ToLowerInvariant();
					file.IsImage = file.Extension is "png" or "jpg" or "jpeg";
				}
				if (file.IsImage)
				{
					await SaveImageAsync(file);
					return;
				}

                file.ActionText = $"Loading {file.FileName}...";

                var loadedLayerCount = file.Extension.Equals(
                    "zip",
                    StringComparison.OrdinalIgnoreCase)
                    ? await ExtractAndLoadArchiveAsync(localPath)
                    : await LoadSpatialFileAsync(localPath);

                file.ActionText = loadedLayerCount == 1
                    ? $"Loaded: {file.FileName}"
                    : $"Loaded {loadedLayerCount} layers: {file.FileName}";
                StatusText = "Result loaded into the RASID group";
            }
            catch (Exception ex)
            {
                file.ActionText = $"Retry: {file.FileName}";
                file.IsActionEnabled = true;
                ArcGIS.Desktop.Framework.Dialogs.MessageBox.Show(
                    $"The file could not be downloaded or loaded:\n\n{ex.Message}",
                    "GoPilot File");
            }
        }

        private async Task SaveImageAsync(ChatFileAttachment file)
        {
            try
            {
                file.ActionText = $"Preparing {file.FileName}...";
                var localPath = File.Exists(file.LocalPath)
                    ? file.LocalPath
                    : await _rasidApi.DownloadFileAsync(file.Url);
                file.LocalPath = localPath;

                var dialog = new Microsoft.Win32.SaveFileDialog
                {
                    FileName = file.FileName,
                    DefaultExt = "." + file.Extension,
                    Filter = $"{file.Extension.ToUpperInvariant()} image (*.{file.Extension})|*.{file.Extension}|All files (*.*)|*.*"
                };

                if (dialog.ShowDialog() == true)
                {
                    File.Copy(localPath, dialog.FileName, overwrite: true);
                    file.ActionText = $"Saved: {file.FileName}";
                }
                else
                {
                    file.ActionText = $"Save {file.FileName}";
                }
            }
            catch (Exception ex)
            {
                file.ActionText = $"Retry Save: {file.FileName}";
                ArcGIS.Desktop.Framework.Dialogs.MessageBox.Show(
                    $"The image could not be saved:\n\n{ex.Message}",
                    "Save GoPilot Image");
            }
            finally
            {
                file.IsActionEnabled = true;
            }
        }

        private static async Task<int> LoadSpatialFileAsync(string localPath)
        {
            var layerName = Path.GetFileNameWithoutExtension(localPath);
            await LayerLoader.LoadResultAsync(localPath, layerName);
            return 1;
        }

        private static async Task<int> ExtractAndLoadArchiveAsync(string zipPath)
        {
            var downloadRoot = Path.Combine(
                Path.GetTempPath(),
                "rasid_downloads");
            var extractionRoot = Path.Combine(
                downloadRoot,
                $"{Path.GetFileNameWithoutExtension(zipPath)}_{Guid.NewGuid():N}");
            Directory.CreateDirectory(extractionRoot);

            var safeRoot = Path.GetFullPath(extractionRoot)
                .TrimEnd(Path.DirectorySeparatorChar) +
                Path.DirectorySeparatorChar;

            using (var archive = ZipFile.OpenRead(zipPath))
            {
                foreach (var entry in archive.Entries)
                {
                    if (string.IsNullOrEmpty(entry.Name))
                        continue;

                    var destination = Path.GetFullPath(
                        Path.Combine(extractionRoot, entry.FullName));
                    if (!destination.StartsWith(
                        safeRoot,
                        StringComparison.OrdinalIgnoreCase))
                    {
                        throw new InvalidDataException(
                            "The ZIP file contains an unsafe path.");
                    }

                    Directory.CreateDirectory(
                        Path.GetDirectoryName(destination)!);
                    entry.ExtractToFile(destination, overwrite: true);
                }
            }

            var supportedLayerExtensions = new HashSet<string>(
                new[] { ".tif", ".tiff", ".shp", ".geojson", ".gpkg" },
                StringComparer.OrdinalIgnoreCase);
            var layerFiles = Directory
                .EnumerateFiles(
                    extractionRoot,
                    "*",
                    SearchOption.AllDirectories)
                .Where(path => supportedLayerExtensions.Contains(
                    Path.GetExtension(path)))
                .ToList();

            if (layerFiles.Count == 0)
            {
                throw new InvalidDataException(
                    "The ZIP file does not contain a supported spatial layer.");
            }

            foreach (var layerFile in layerFiles)
                await LoadSpatialFileAsync(layerFile);

            return layerFiles.Count;
        }

        private void RefreshLastMessage()
        {
            if (Messages.Count == 0)
                return;

            var index = Messages.Count - 1;
            var item = Messages[index];
            Messages.RemoveAt(index);
            Messages.Insert(index, item);
            NotifyPropertyChanged(nameof(HasMessages));
        }

        public void Dispose()
        {
            _geoManager.GeometryReady -= OnGeometryReady;
            _geoManager.DrawCancelled -= OnDrawCancelled;
            _geoManager.Dispose();
        }
    }
}
