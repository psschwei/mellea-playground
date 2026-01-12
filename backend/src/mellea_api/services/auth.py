"""Authentication service for user management and authentication."""

import logging
from datetime import datetime

from mellea_api.core.config import Settings, get_settings
from mellea_api.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from mellea_api.core.store import JsonStore
from mellea_api.models.user import (
    AuthProvider,
    TokenResponse,
    User,
    UserCreate,
    UserPublic,
    UserQuotas,
    UserRole,
    UserStatus,
)

logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Raised when authentication fails."""

    pass


class RegistrationError(Exception):
    """Raised when user registration fails."""

    pass


class AuthService:
    """Service for user authentication and management."""

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize the auth service.

        Args:
            settings: Application settings (uses default if not provided)
        """
        self.settings = settings or get_settings()
        self._store: JsonStore[User] | None = None

    @property
    def store(self) -> JsonStore[User]:
        """Get the user store, initializing if needed."""
        if self._store is None:
            file_path = self.settings.data_dir / "metadata" / "users.json"
            self._store = JsonStore[User](
                file_path=file_path,
                collection_key="users",
                model_class=User,
            )
        return self._store

    def get_user_by_email(self, email: str) -> User | None:
        """Get a user by email address.

        Args:
            email: User's email address

        Returns:
            User if found, None otherwise
        """
        users = self.store.find(lambda u: u.email.lower() == email.lower())
        return users[0] if users else None

    def get_user_by_id(self, user_id: str) -> User | None:
        """Get a user by ID.

        Args:
            user_id: User's unique identifier

        Returns:
            User if found, None otherwise
        """
        return self.store.get_by_id(user_id)

    def authenticate(self, email: str, password: str) -> User:
        """Authenticate a user with email and password.

        Args:
            email: User's email address
            password: User's password

        Returns:
            Authenticated user

        Raises:
            AuthenticationError: If credentials are invalid or account is not active
        """
        user = self.get_user_by_email(email)

        if user is None:
            raise AuthenticationError("Invalid email or password")

        if user.password_hash is None:
            raise AuthenticationError("Account uses external authentication")

        if not verify_password(password, user.password_hash):
            raise AuthenticationError("Invalid email or password")

        if user.status != UserStatus.ACTIVE:
            raise AuthenticationError(f"Account is {user.status.value}")

        # Update last login time
        user.last_login_at = datetime.utcnow()
        user.updated_at = datetime.utcnow()
        self.store.update(user.id, user)

        return user

    def create_user(self, user_data: UserCreate, role: UserRole = UserRole.END_USER) -> User:
        """Create a new user account.

        Args:
            user_data: User registration data
            role: Role to assign to the user

        Returns:
            Created user

        Raises:
            RegistrationError: If email already exists
        """
        # Check for existing user
        if self.get_user_by_email(user_data.email):
            raise RegistrationError("Email already registered")

        # Create user with hashed password
        user = User(
            email=user_data.email,
            display_name=user_data.display_name,
            username=user_data.username,
            password_hash=hash_password(user_data.password),
            auth_provider=AuthProvider.LOCAL,
            role=role,
            status=UserStatus.ACTIVE,
            quotas=UserQuotas(),
        )

        self.store.create(user)
        logger.info(f"Created user: {user.email} with role {user.role.value}")

        return user

    def login(self, email: str, password: str) -> TokenResponse:
        """Login a user and return a token response.

        Args:
            email: User's email address
            password: User's password

        Returns:
            Token response with JWT and user info

        Raises:
            AuthenticationError: If credentials are invalid
        """
        user = self.authenticate(email, password)

        token, expires_at = create_access_token(
            user_id=user.id,
            email=user.email,
            name=user.display_name,
            role=user.role,
        )

        return TokenResponse(
            token=token,
            expires_at=expires_at,
            user=UserPublic.model_validate(user),
        )

    def register(self, user_data: UserCreate) -> TokenResponse:
        """Register a new user and return a token response.

        Args:
            user_data: User registration data

        Returns:
            Token response with JWT and user info

        Raises:
            RegistrationError: If registration fails
        """
        user = self.create_user(user_data)

        token, expires_at = create_access_token(
            user_id=user.id,
            email=user.email,
            name=user.display_name,
            role=user.role,
        )

        return TokenResponse(
            token=token,
            expires_at=expires_at,
            user=UserPublic.model_validate(user),
        )

    def seed_default_users(self) -> None:
        """Seed default development users if they don't exist."""
        default_users = [
            {
                "email": "admin@mellea.dev",
                "password": "admin123",
                "display_name": "Admin User",
                "role": UserRole.ADMIN,
            },
            {
                "email": "developer@mellea.dev",
                "password": "dev123",
                "display_name": "Developer User",
                "role": UserRole.DEVELOPER,
            },
            {
                "email": "user@mellea.dev",
                "password": "user123",
                "display_name": "End User",
                "role": UserRole.END_USER,
            },
        ]

        for user_data in default_users:
            if not self.get_user_by_email(user_data["email"]):
                user = User(
                    email=user_data["email"],
                    display_name=user_data["display_name"],
                    password_hash=hash_password(user_data["password"]),
                    auth_provider=AuthProvider.LOCAL,
                    role=user_data["role"],
                    status=UserStatus.ACTIVE,
                    quotas=self._get_default_quotas(user_data["role"]),
                )
                self.store.create(user)
                logger.info(f"Seeded default user: {user.email}")

    def _get_default_quotas(self, role: UserRole) -> UserQuotas:
        """Get default quotas based on role."""
        if role == UserRole.ADMIN:
            return UserQuotas(
                max_concurrent_runs=10,
                max_storage_mb=50000,
                max_cpu_hours_per_month=1000,
                max_runs_per_day=500,
            )
        elif role == UserRole.DEVELOPER:
            return UserQuotas(
                max_concurrent_runs=5,
                max_storage_mb=10000,
                max_cpu_hours_per_month=200,
                max_runs_per_day=100,
            )
        else:
            return UserQuotas()


# Global service instance
_auth_service: AuthService | None = None


def get_auth_service() -> AuthService:
    """Get the global auth service instance."""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service
