# Telegram Message Forwarder

A robust Telegram Bot Forwarding System

An advanced Telegram bot with dual-client architecture for intelligent message forwarding between channels, featuring PostgreSQL database, Redis queuing, and comprehensive management tools.

## Features

### **Core Functionality**
- **Dual-Client Architecture**: Bot API (python-telegram-bot) + MTProto (Telethon) for maximum compatibility
- **Smart Forwarding**: Two modes - `forward_message` (preserve author) vs `copy_message` (copy content)
- **Private Channel Access**: MTProto client enables access to private channels
- **Queue-Based Processing**: Redis-powered queuing with FloodWait handling and retry logic
- **Message Deduplication**: Hash-based deduplication prevents duplicate forwards

### **Advanced Management**
- **Interactive UI**: Modern inline keyboards with pagination and multi-select
- **State Management**: Multi-step workflows with input validation
- **Legacy Compatibility**: Seamless migration from existing bot functionality
- **Admin Panel**: Comprehensive system administration and monitoring
- **Migration Tools**: Automated SQLite to PostgreSQL migration

### **Enterprise Features**
- **PostgreSQL Database**: Scalable database with SQLAlchemy 2.0 async ORM
- **Structured Logging**: JSON logging with structlog for observability
- **CLI Management**: Command-line tools for migration and administration
- **Environment Configuration**: Secure configuration management
- **Graceful Shutdown**: Proper lifecycle management with signal handling

## Requirements
- **QueueManager**: Redis-based priority queue for forwarding tasks
- **DeduplicationService**: Prevents duplicate message forwarding
- **ChannelService**: Manages channel subscriptions and access
- **MappingService**: Handles source-to-destination channel mappings

### Database
- **PostgreSQL**: Primary database with SQLAlchemy ORM
- **Redis**: Caching, queuing, and deduplication
- **Alembic**: Database migrations

## Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL 14+
- Redis 7.x
- Docker & Docker Compose (optional)

### Installation

1. Clone the repository:
```bash
git clone <git@github.com:AvonT1/mymoreac_messeng_bot.git>
cd MultiSelectChannels
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

4. Run database migrations:
```bash
alembic upgrade head
```

5. Start the application:
```bash
python main.py
```

### Docker Setup

1. Build and start services:
```bash
docker-compose up -d
```

2. Run migrations:
```bash
docker-compose exec app alembic upgrade head
```

## Configuration

### Required Environment Variables

- `BOT_TOKEN`: Telegram bot token from @BotFather
- `API_ID`: Telegram API ID from my.telegram.org
- `API_HASH`: Telegram API hash from my.telegram.org
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string
- `ADMIN_IDS`: Comma-separated list of admin user IDs

### Optional Variables

- `USER_SESSION_FILE_PATH`: Path to Telethon session file (default: sessions/user.session)
- `MAX_CONCURRENT_FORWARDS`: Maximum concurrent forwarding tasks (default: 10)
- `ENCRYPTION_KEY`: Key for encrypting session files
- `DEBUG_MODE`: Enable debug logging (default: false)
- `LOG_LEVEL`: Logging level (default: INFO)
- `SENTRY_DSN`: Sentry DSN for error tracking

## Usage

### Bot Commands

- `/start` - Start the bot and show main menu
- `/help` - Show help information
- `/admin` - Admin panel (admin users only)

### Channel Management

1. Use the bot menu to add source and destination channels
2. Create mappings between source and destination channels
3. Configure forwarding modes (forward vs copy)
4. Set up filters and rules

### Forwarding Modes

- **Forward Mode**: Preserves original author information (requires bot access to both channels)
- **Copy Mode**: Copies message content without original author (fallback mode)

## Development

### Project Structure

```
app/
├── clients/          # Bot and user client implementations
├── core/             # Core forwarding logic and queue management
├── database/         # Database models and engine
├── handlers/         # Message and command handlers
├── services/         # Business logic services
└── utils/            # Utilities and helpers

migrations/           # Alembic database migrations
sessions/            # Telegram session files
logs/                # Application logs
```

### Adding New Features

1. Create feature branch
2. Implement changes following existing patterns
3. Add tests if applicable
4. Update documentation
5. Submit pull request

### Database Migrations

Create new migration:
```bash
alembic revision --autogenerate -m "Description"
```

Apply migrations:
```bash
alembic upgrade head
```

## Monitoring

The application includes built-in monitoring with metrics collection:

- Message forwarding rates
- Error rates and types
- Queue sizes and processing times
- Client connection status

Metrics are stored in Redis and can be exported to monitoring systems like Prometheus.

## Security

- Session files are encrypted using Fernet encryption
- Admin access is validated for sensitive operations
- Input sanitization prevents injection attacks
- Rate limiting protects against abuse

## Troubleshooting

### Common Issues

1. **FloodWait errors**: The bot automatically handles Telegram rate limits with exponential backoff
2. **Session issues**: Delete session files and re-authenticate if needed
3. **Database connection**: Ensure PostgreSQL is running and accessible
4. **Redis connection**: Verify Redis is running and connection string is correct

### Logs

Check application logs in:
- Console output (when running directly)
- `logs/` directory (file logging)
- Docker logs: `docker-compose logs app`

### Debug Mode

Enable debug mode for verbose logging:
```bash
export DEBUG_MODE=true
python main.py
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support and questions:
- Create an issue on GitHub
- Check the troubleshooting section
- Review the logs for error details
