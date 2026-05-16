import axios, { AxiosInstance, AxiosRequestConfig } from 'axios';
import { config as appConfig } from '../config/index.js';

class HttpClient {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      timeout: appConfig.webhookTimeout,
      headers: {
        'Content-Type': 'application/json',
      },
    });
  }

  async get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.client.get<T>(url, config);
    return response.data;
  }

  async post<T>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.client.post<T>(url, data, config);
    return response.data;
  }

  async request<T>(config: AxiosRequestConfig): Promise<T> {
    const response = await this.client.request<T>(config);
    return response.data;
  }
}

export const httpClient = new HttpClient();
