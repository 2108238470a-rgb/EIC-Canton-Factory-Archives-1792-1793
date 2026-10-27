import {
    Document,
    DocumentListResponse,
    Page,
    Block,
    BlockListResponse,
    Task,
    Export,
    ExportListResponse,
    RunOCRRequest,
    RunPolishRequest,
    ExportRequest,
    BlockUpdateRequest,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

class ApiError extends Error {
    constructor(
        public status: number,
        message: string
    ) {
        super(message);
        this.name = "ApiError";
    }
}

async function fetchApi<T>(
    endpoint: string,
    options?: RequestInit
): Promise<T> {
    const url = `${API_BASE}/api${endpoint}`;
    const response = await fetch(url, {
        ...options,
        headers: {
            "Content-Type": "application/json",
            ...options?.headers,
        },
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new ApiError(
            response.status,
            error.error?.message || response.statusText
        );
    }

    return response.json();
}

// Document API
export const documentApi = {
    upload: async (file: File): Promise<Document> => {
        const formData = new FormData();
        formData.append("file", file);

        const response = await fetch(`${API_BASE}/api/documents/upload`, {
            method: "POST",
            body: formData,
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new ApiError(
                response.status,
                error.error?.message || "Upload failed"
            );
        }

        return response.json();
    },

    list: (page = 1, pageSize = 20): Promise<DocumentListResponse> =>
        fetchApi(`/documents?page=${page}&page_size=${pageSize}`),

    get: (id: number): Promise<Document> => fetchApi(`/documents/${id}`),

    delete: (id: number): Promise<void> =>
        fetchApi(`/documents/${id}`, { method: "DELETE" }),

    runOcr: (id: number, options?: RunOCRRequest): Promise<Task> =>
        fetchApi(`/documents/${id}/run-ocr`, {
            method: "POST",
            body: JSON.stringify(options || {}),
        }),

    getPages: (id: number): Promise<{ items: Page[]; total: number }> =>
        fetchApi(`/documents/${id}/pages`),

    runPolish: (id: number, options?: RunPolishRequest): Promise<Task> =>
        fetchApi(`/blocks/documents/${id}/run-polish`, {
            method: "POST",
            body: JSON.stringify(options || {}),
        }),
};

// Page API
export const pageApi = {
    get: (id: number): Promise<Page> => fetchApi(`/pages/${id}`),

    getBlocks: (id: number): Promise<BlockListResponse> =>
        fetchApi(`/pages/${id}/blocks`),

    getImageUrl: (id: number): string => `${API_BASE}/api/pages/${id}/image`,

    getVisualizationUrl: (id: number): string =>
        `${API_BASE}/api/pages/${id}/visualization`,

    runPolish: (id: number, options?: RunPolishRequest): Promise<Task> =>
        fetchApi(`/blocks/pages/${id}/run-polish`, {
            method: "POST",
            body: JSON.stringify(options || {}),
        }),
};

// Block API
export const blockApi = {
    get: (id: number): Promise<Block> => fetchApi(`/blocks/${id}`),

    update: (id: number, data: BlockUpdateRequest): Promise<Block> =>
        fetchApi(`/blocks/${id}`, {
            method: "PATCH",
            body: JSON.stringify(data),
        }),

    runPolish: (id: number, options?: RunPolishRequest): Promise<Task> =>
        fetchApi(`/blocks/${id}/run-polish`, {
            method: "POST",
            body: JSON.stringify(options || {}),
        }),
};

// Task API
export const taskApi = {
    get: (id: number): Promise<Task> => fetchApi(`/tasks/${id}`),

    poll: async (
        id: number,
        onProgress?: (task: Task) => void,
        interval = 5000
    ): Promise<Task> => {
        return new Promise((resolve, reject) => {
            const check = async () => {
                try {
                    const task = await taskApi.get(id);
                    onProgress?.(task);

                    if (task.status === "completed") {
                        resolve(task);
                    } else if (task.status === "failed") {
                        reject(new Error(task.error_message || "Task failed"));
                    } else {
                        setTimeout(check, interval);
                    }
                } catch (error) {
                    reject(error);
                }
            };
            check();
        });
    },
};

// Export API
export const exportApi = {
    create: (documentId: number, format: ExportRequest): Promise<Export> =>
        fetchApi(`/exports/documents/${documentId}/export`, {
            method: "POST",
            body: JSON.stringify(format),
        }),

    list: (documentId: number): Promise<ExportListResponse> =>
        fetchApi(`/exports/documents/${documentId}/exports`),

    getDownloadUrl: (exportId: number): string =>
        `${API_BASE}/api/exports/${exportId}/download`,
};

export { ApiError };
