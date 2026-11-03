import { Controller, Get } from '@nestjs/common';
import { AppService } from './app.service';

@Controller()
export class AppController {
  constructor(private readonly appService: AppService) {}

  @Get('hello')  // This will become /api/hello due to global prefix
  getHelloWorld(): string {
    return this.appService.getHello();
  }
}