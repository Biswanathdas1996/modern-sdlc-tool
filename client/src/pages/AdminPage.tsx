import { useState, useEffect } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Users,
  UserPlus,
  Shield,
  ShieldCheck,
  Loader2,
  Trash2,
  Key,
  ToggleLeft,
  Check,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/use-toast";
import { apiRequest, queryClient } from "@/lib/queryClient";

interface Feature {
  key: string;
  label: string;
  category: string;
}

interface UserData {
  id: string;
  username: string;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
  permissions: string[];
}

export default function AdminPage() {
  const { user: currentUser } = useAuth();
  const { toast } = useToast();
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showPermissionsDialog, setShowPermissionsDialog] = useState(false);
  const [showPasswordDialog, setShowPasswordDialog] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [selectedUser, setSelectedUser] = useState<UserData | null>(null);
  const [selectedPermissions, setSelectedPermissions] = useState<string[]>([]);

  const [newUsername, setNewUsername] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState("user");
  const [newFeatures, setNewFeatures] = useState<string[]>([]);
  const [resetPassword, setResetPassword] = useState("");

  useEffect(() => {
    document.title = "Admin Dashboard | Defuse 2.O";
  }, []);

  const { data: users = [], isLoading: usersLoading } = useQuery<UserData[]>({
    queryKey: ["/api/admin/users"],
  });

  const { data: features = [] } = useQuery<Feature[]>({
    queryKey: ["/api/auth/features"],
  });

  const createUserMutation = useMutation({
    mutationFn: async (data: { username: string; email: string; password: string; role: string; features: string[] }) => {
      const res = await apiRequest("POST", "/api/admin/users", data);
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/admin/users"] });
      setShowCreateDialog(false);
      setNewUsername("");
      setNewEmail("");
      setNewPassword("");
      setNewRole("user");
      setNewFeatures([]);
      toast({ title: "User created", description: "New user account has been created" });
    },
    onError: (err: Error) => {
      toast({ title: "Failed to create user", description: err.message, variant: "destructive" });
    },
  });

  const updatePermissionsMutation = useMutation({
    mutationFn: async ({ userId, features }: { userId: string; features: string[] }) => {
      const res = await apiRequest("PATCH", `/api/admin/users/${userId}/permissions`, { features });
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/admin/users"] });
      setShowPermissionsDialog(false);
      toast({ title: "Permissions updated", description: "User permissions have been saved" });
    },
    onError: (err: Error) => {
      toast({ title: "Failed to update permissions", description: err.message, variant: "destructive" });
    },
  });

  const toggleStatusMutation = useMutation({
    mutationFn: async ({ userId, isActive }: { userId: string; isActive: boolean }) => {
      const res = await apiRequest("PATCH", `/api/admin/users/${userId}/status`, { is_active: isActive });
      return res.json();
    },
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ["/api/admin/users"] });
      toast({
        title: vars.isActive ? "User activated" : "User deactivated",
        description: `Account has been ${vars.isActive ? "activated" : "deactivated"}`,
      });
    },
    onError: (err: Error) => {
      toast({ title: "Failed to update status", description: err.message, variant: "destructive" });
    },
  });

  const resetPasswordMutation = useMutation({
    mutationFn: async ({ userId, password }: { userId: string; password: string }) => {
      const res = await apiRequest("PATCH", `/api/admin/users/${userId}/password`, { password });
      return res.json();
    },
    onSuccess: () => {
      setShowPasswordDialog(false);
      setResetPassword("");
      toast({ title: "Password reset", description: "User password has been updated" });
    },
    onError: (err: Error) => {
      toast({ title: "Failed to reset password", description: err.message, variant: "destructive" });
    },
  });

  const deleteUserMutation = useMutation({
    mutationFn: async (userId: string) => {
      const res = await apiRequest("DELETE", `/api/admin/users/${userId}`);
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/admin/users"] });
      setShowDeleteDialog(false);
      toast({ title: "User deleted", description: "User account has been removed" });
    },
    onError: (err: Error) => {
      toast({ title: "Failed to delete user", description: err.message, variant: "destructive" });
    },
  });

  const openPermissions = (u: UserData) => {
    setSelectedUser(u);
    setSelectedPermissions([...u.permissions]);
    setShowPermissionsDialog(true);
  };

  const toggleFeature = (key: string) => {
    setSelectedPermissions(prev =>
      prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]
    );
  };

  const toggleNewFeature = (key: string) => {
    setNewFeatures(prev =>
      prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]
    );
  };

  const groupedFeatures = features.reduce<Record<string, Feature[]>>((acc, f) => {
    if (!acc[f.category]) acc[f.category] = [];
    acc[f.category].push(f);
    return acc;
  }, {});

  const categoryLabels: Record<string, string> = {
    prerequisite: "Pre-requisite Steps",
    workflow: "Workflow Steps",
    tools: "Tools",
    agents: "AI Agents",
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-5xl mx-auto p-6 space-y-6">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary">
              <Shield className="h-5 w-5 text-primary-foreground" />
            </div>
            <div>
              <h1 className="text-2xl font-bold" data-testid="text-admin-title">Admin Dashboard</h1>
              <p className="text-sm text-muted-foreground">
                Manage users and feature access
              </p>
            </div>
          </div>
          <Button onClick={() => setShowCreateDialog(true)} data-testid="button-create-user">
            <UserPlus className="h-4 w-4 mr-2" />
            Create User
          </Button>
        </div>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Users className="h-4 w-4" />
              Users ({users.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            {usersLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : users.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-8">No users found</p>
            ) : (
              <div className="space-y-3">
                {users.map((u) => (
                  <div
                    key={u.id}
                    className={cn(
                      "flex items-center justify-between gap-3 p-4 rounded-md border border-border flex-wrap",
                      !u.is_active && "opacity-60"
                    )}
                    data-testid={`user-row-${u.username}`}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className={cn(
                        "flex h-9 w-9 shrink-0 items-center justify-center rounded-full",
                        u.role === "admin" ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
                      )}>
                        {u.role === "admin" ? <ShieldCheck className="h-4 w-4" /> : <Users className="h-4 w-4" />}
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-medium text-sm">{u.username}</span>
                          <Badge variant={u.role === "admin" ? "default" : "secondary"} className="text-xs">
                            {u.role}
                          </Badge>
                          {!u.is_active && (
                            <Badge variant="outline" className="text-xs text-destructive border-destructive/30">
                              Disabled
                            </Badge>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground truncate">{u.email}</p>
                        <div className="flex items-center gap-1 mt-1 flex-wrap">
                          <span className="text-xs text-muted-foreground">{u.permissions.length} features</span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => openPermissions(u)}
                        title="Manage permissions"
                        data-testid={`button-permissions-${u.username}`}
                      >
                        <ShieldCheck className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => { setSelectedUser(u); setShowPasswordDialog(true); }}
                        title="Reset password"
                        data-testid={`button-reset-pwd-${u.username}`}
                      >
                        <Key className="h-4 w-4" />
                      </Button>
                      {u.id !== currentUser?.id && (
                        <>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => toggleStatusMutation.mutate({ userId: u.id, isActive: !u.is_active })}
                            title={u.is_active ? "Deactivate" : "Activate"}
                            data-testid={`button-toggle-${u.username}`}
                          >
                            <ToggleLeft className={cn("h-4 w-4", u.is_active ? "text-green-500" : "text-muted-foreground")} />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => { setSelectedUser(u); setShowDeleteDialog(true); }}
                            title="Delete user"
                            data-testid={`button-delete-${u.username}`}
                          >
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
          <DialogContent className="sm:max-w-lg" data-testid="dialog-create-user">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <UserPlus className="h-5 w-5" />
                Create New User
              </DialogTitle>
              <DialogDescription>
                Add a new user and assign their feature access
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-2">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label htmlFor="create-username">Username</Label>
                  <Input
                    id="create-username"
                    value={newUsername}
                    onChange={(e) => setNewUsername(e.target.value)}
                    placeholder="johndoe"
                    data-testid="input-create-username"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="create-role">Role</Label>
                  <Select value={newRole} onValueChange={setNewRole}>
                    <SelectTrigger data-testid="select-create-role">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="user">User</SelectItem>
                      <SelectItem value="admin">Admin</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="create-email">Email</Label>
                <Input
                  id="create-email"
                  type="email"
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  placeholder="john@example.com"
                  data-testid="input-create-email"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="create-password">Password</Label>
                <Input
                  id="create-password"
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Minimum 6 characters"
                  data-testid="input-create-password"
                />
              </div>

              {newRole === "user" && (
                <div className="space-y-3">
                  <Label>Feature Access</Label>
                  <div className="max-h-48 overflow-y-auto space-y-3 border border-border rounded-md p-3">
                    {Object.entries(groupedFeatures).map(([category, feats]) => (
                      <div key={category}>
                        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1.5">
                          {categoryLabels[category] || category}
                        </p>
                        <div className="space-y-1">
                          {feats.map((f) => (
                            <label
                              key={f.key}
                              className="flex items-center justify-between gap-2 py-1 cursor-pointer"
                            >
                              <span className="text-sm">{f.label}</span>
                              <Switch
                                checked={newFeatures.includes(f.key)}
                                onCheckedChange={() => toggleNewFeature(f.key)}
                                data-testid={`switch-create-${f.key}`}
                              />
                            </label>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => setNewFeatures(features.map(f => f.key))}
                      data-testid="button-select-all-create"
                    >
                      <Check className="h-3 w-3 mr-1" />
                      Select All
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => setNewFeatures([])}
                      data-testid="button-clear-all-create"
                    >
                      <X className="h-3 w-3 mr-1" />
                      Clear All
                    </Button>
                  </div>
                </div>
              )}
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setShowCreateDialog(false)}>Cancel</Button>
              <Button
                onClick={() => createUserMutation.mutate({
                  username: newUsername.trim(),
                  email: newEmail.trim(),
                  password: newPassword,
                  role: newRole,
                  features: newRole === "admin" ? features.map(f => f.key) : newFeatures,
                })}
                disabled={!newUsername.trim() || !newEmail.trim() || !newPassword || newPassword.length < 6 || createUserMutation.isPending}
                data-testid="button-submit-create"
              >
                {createUserMutation.isPending ? (
                  <><Loader2 className="h-4 w-4 animate-spin mr-2" />Creating...</>
                ) : (
                  "Create User"
                )}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog open={showPermissionsDialog} onOpenChange={setShowPermissionsDialog}>
          <DialogContent className="sm:max-w-lg" data-testid="dialog-permissions">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <ShieldCheck className="h-5 w-5" />
                Manage Permissions
              </DialogTitle>
              <DialogDescription>
                {selectedUser && `Configure feature access for ${selectedUser.username}`}
              </DialogDescription>
            </DialogHeader>
            <div className="max-h-72 overflow-y-auto space-y-3 py-2">
              {Object.entries(groupedFeatures).map(([category, feats]) => (
                <div key={category}>
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1.5">
                    {categoryLabels[category] || category}
                  </p>
                  <div className="space-y-1">
                    {feats.map((f) => (
                      <label
                        key={f.key}
                        className="flex items-center justify-between gap-2 py-1 cursor-pointer"
                      >
                        <span className="text-sm">{f.label}</span>
                        <Switch
                          checked={selectedPermissions.includes(f.key)}
                          onCheckedChange={() => toggleFeature(f.key)}
                          data-testid={`switch-perm-${f.key}`}
                        />
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setSelectedPermissions(features.map(f => f.key))}
                data-testid="button-select-all-perms"
              >
                <Check className="h-3 w-3 mr-1" />
                Select All
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setSelectedPermissions([])}
                data-testid="button-clear-all-perms"
              >
                <X className="h-3 w-3 mr-1" />
                Clear All
              </Button>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setShowPermissionsDialog(false)}>Cancel</Button>
              <Button
                onClick={() => selectedUser && updatePermissionsMutation.mutate({
                  userId: selectedUser.id,
                  features: selectedPermissions,
                })}
                disabled={updatePermissionsMutation.isPending}
                data-testid="button-save-permissions"
              >
                {updatePermissionsMutation.isPending ? (
                  <><Loader2 className="h-4 w-4 animate-spin mr-2" />Saving...</>
                ) : (
                  "Save Permissions"
                )}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog open={showPasswordDialog} onOpenChange={setShowPasswordDialog}>
          <DialogContent className="sm:max-w-sm" data-testid="dialog-reset-password">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Key className="h-5 w-5" />
                Reset Password
              </DialogTitle>
              <DialogDescription>
                {selectedUser && `Set a new password for ${selectedUser.username}`}
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-3 py-2">
              <div className="space-y-2">
                <Label htmlFor="reset-password">New Password</Label>
                <Input
                  id="reset-password"
                  type="password"
                  value={resetPassword}
                  onChange={(e) => setResetPassword(e.target.value)}
                  placeholder="Minimum 6 characters"
                  data-testid="input-reset-password"
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => { setShowPasswordDialog(false); setResetPassword(""); }}>Cancel</Button>
              <Button
                onClick={() => selectedUser && resetPasswordMutation.mutate({ userId: selectedUser.id, password: resetPassword })}
                disabled={!resetPassword || resetPassword.length < 6 || resetPasswordMutation.isPending}
                data-testid="button-submit-reset-password"
              >
                {resetPasswordMutation.isPending ? (
                  <><Loader2 className="h-4 w-4 animate-spin mr-2" />Resetting...</>
                ) : (
                  "Reset Password"
                )}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
          <DialogContent className="sm:max-w-sm" data-testid="dialog-delete-user">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Trash2 className="h-5 w-5 text-destructive" />
                Delete User
              </DialogTitle>
              <DialogDescription>
                {selectedUser && `Are you sure you want to delete ${selectedUser.username}? This action cannot be undone.`}
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setShowDeleteDialog(false)}>Cancel</Button>
              <Button
                variant="destructive"
                onClick={() => selectedUser && deleteUserMutation.mutate(selectedUser.id)}
                disabled={deleteUserMutation.isPending}
                data-testid="button-confirm-delete"
              >
                {deleteUserMutation.isPending ? (
                  <><Loader2 className="h-4 w-4 animate-spin mr-2" />Deleting...</>
                ) : (
                  "Delete User"
                )}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  );
}
