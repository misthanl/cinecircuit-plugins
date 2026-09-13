import { ref, type Ref } from "vue";
import type { MediaItem, OnlineSubtitle, SourceStatus, ManualAction, CaptchaChallenge, PreviewItem, OnlineResponse, PreviewResponse, Requester } from "./workspaceTypes";

const list = <T>(value: T[] | undefined): T[] => Array.isArray(value) ? value : [];

export class SubtitleOnlineSession {
  readonly online = ref<OnlineSubtitle[]>([]);
  readonly onlineQuery = ref("");
  readonly sourceStatuses = ref<SourceStatus[]>([]);
  readonly activeSource = ref("");
  readonly manualActions = ref<ManualAction[]>([]);
  readonly captchaChallenges = ref<CaptchaChallenge[]>([]);
  readonly selectedCandidate = ref("");
  readonly previewToken = ref("");
  readonly previewItems = ref<PreviewItem[]>([]);
  readonly previewSelected = ref<number[]>([]);
  readonly activePreviewIndex = ref<number | null>(null);
  readonly previewing = ref(false);
  readonly previewCaptcha = ref<CaptchaChallenge | null>(null);
  readonly captchaInput = ref("");
  readonly solvingCaptcha = ref(false);
  readonly seasonPack = ref(false);
  readonly searching = ref(false);
  private searchSequence = 0;
  private previewSequence = 0;

  constructor(private request: Requester, private selected: Ref<MediaItem | null>, private error: Ref<string>, private status: Ref<string>) {}

  resetPreview() {
    this.previewToken.value = "";
    this.previewItems.value = [];
    this.previewSelected.value = [];
    this.activePreviewIndex.value = null;
    this.previewCaptcha.value = null;
    this.captchaInput.value = "";
  }

  resetResults() {
    this.online.value = [];
    this.selectedCandidate.value = "";
    this.sourceStatuses.value = [];
    this.activeSource.value = "";
    this.manualActions.value = [];
    this.captchaChallenges.value = [];
    this.resetPreview();
  }

  reset() {
    this.searchSequence += 1;
    this.previewSequence += 1;
    this.searching.value = false;
    this.previewing.value = false;
    this.solvingCaptcha.value = false;
    this.resetResults();
  }

  private isSearchCurrent(id: number, path: string) {
    return id === this.searchSequence && this.selected.value?.path === path;
  }

  private isPreviewCurrent(id: number, path: string) {
    return id === this.previewSequence && this.selected.value?.path === path;
  }

  private applySearch(result: OnlineResponse, emptyMessage = "在线字幕源暂无匹配结果") {
    this.online.value = list(result?.items);
    this.sourceStatuses.value = list(result?.sources);
    this.manualActions.value = list(result?.manual_actions);
    this.captchaChallenges.value = list(result?.captcha_challenges);
    this.selectedCandidate.value = "";
    this.status.value = this.online.value.length ? `找到 ${this.online.value.length} 条在线字幕` : emptyMessage;
  }

  private applyPreview(result: PreviewResponse) {
    if (result.captcha_required && result.captcha) {
      this.previewCaptcha.value = result.captcha;
      this.status.value = "该字幕下载前需要验证码，请完成后继续预览";
      return;
    }
    this.previewToken.value = result.preview_handle;
    this.previewItems.value = Array.isArray(result.items) ? result.items : [];
    this.previewSelected.value = this.previewItems.value.map((item) => item.index);
    this.activePreviewIndex.value = this.previewItems.value[0]?.index ?? null;
    this.previewCaptcha.value = null;
    this.captchaInput.value = "";
    this.status.value = `已下载并校验 ${this.previewItems.value.length} 个字幕文件，请确认后保存`;
  }

  async search() {
    if (!this.selected.value || this.searching.value) return;
    this.reset();
    const requestId = ++this.searchSequence;
    const mediaPath = this.selected.value.path;
    const query = this.onlineQuery.value;
    const seasonPack = this.seasonPack.value;
    this.searching.value = true;
    this.error.value = "";
    try {
      const result = await this.request<OnlineResponse>("/plugins/subtitle-manager/api/online-search", {
        method: "POST", body: JSON.stringify({ media_path: mediaPath, query, season_pack: seasonPack }),
      });
      if (this.isSearchCurrent(requestId, mediaPath)) this.applySearch(result);
    } catch (reason) {
      if (this.isSearchCurrent(requestId, mediaPath))
        this.error.value = reason instanceof Error ? reason.message : "在线字幕搜索失败";
    } finally {
      if (requestId === this.searchSequence) this.searching.value = false;
    }
  }

  async preview(candidateToken: string) {
    if (!this.selected.value || !candidateToken || this.previewing.value) return;
    const requestId = ++this.previewSequence;
    this.solvingCaptcha.value = false;
    const mediaPath = this.selected.value.path;
    this.selectedCandidate.value = candidateToken;
    this.previewing.value = true;
    this.error.value = "";
    // A preview is a new user operation. Do not leave the previous search
    // success mounted, otherwise the host alert stack shows it again beside a
    // download failure and makes the click look like another search.
    this.status.value = "";
    this.resetPreview();
    try {
      const result = await this.request<PreviewResponse>("/plugins/subtitle-manager/api/online-preview", {
        method: "POST", body: JSON.stringify({ media_path: mediaPath, candidate_handle: candidateToken }),
      });
      if (this.isPreviewCurrent(requestId, mediaPath) && this.selectedCandidate.value === candidateToken) this.applyPreview(result);
    } catch (reason) {
      if (this.isPreviewCurrent(requestId, mediaPath))
        this.error.value = reason instanceof Error ? reason.message : "字幕下载预览失败";
    } finally {
      if (requestId === this.previewSequence) this.previewing.value = false;
    }
  }

  private applyCaptcha(result: OnlineResponse | PreviewResponse) {
    if ("captcha_required" in result && result.captcha_required && result.captcha) {
      if (this.previewCaptcha.value) this.previewCaptcha.value = result.captcha;
      else this.captchaChallenges.value = [result.captcha];
      this.captchaInput.value = "";
      return;
    }
    if ("preview_handle" in result && result.preview_handle) {
      this.applyPreview(result);
      return;
    }
    this.applySearch(result as OnlineResponse, "验证码已提交，仍在等待字幕源结果");
    this.activeSource.value = "";
    this.captchaInput.value = "";
  }

  async submitCaptcha(challenge: CaptchaChallenge | null) {
    if (!challenge || this.solvingCaptcha.value || !this.captchaInput.value.trim()) return;
    const code = this.captchaInput.value.trim();
    const generation = this.searchSequence;
    const preview = this.previewSequence;
    const current = () => generation === this.searchSequence && preview === this.previewSequence;
    this.solvingCaptcha.value = true;
    this.error.value = "";
    try {
      const result = await this.request<OnlineResponse | PreviewResponse>("/plugins/subtitle-manager/api/online-captcha", {
        method: "POST", body: JSON.stringify({ captcha_handle: challenge.handle, code }),
      });
      if (current()) this.applyCaptcha(result);
    } catch (reason) {
      if (current()) this.error.value = reason instanceof Error ? reason.message : "验证码提交失败";
    } finally {
      if (current()) this.solvingCaptcha.value = false;
    }
  }
}
